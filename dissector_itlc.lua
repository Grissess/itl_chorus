local itlc = Proto("ITLC", "ITL Chorus Protocol")

local fields = {
	command = ProtoField.new("Command", "itlc.cmd", ftypes.UINT32),
	pingdata = ProtoField.new("Ping Data", "itlc.ping", ftypes.BYTES),
	seconds = ProtoField.new("Seconds", "itlc.secs", ftypes.UINT32),
	microseconds = ProtoField.new("Microseconds", "itlc.usecs", ftypes.UINT32),
	frequency = ProtoField.new("Frequency(Hz)", "itlc.freq", ftypes.UINT32),
	amplitude = ProtoField.new("Amplitude", "itlc.amp", ftypes.FLOAT),
	port = ProtoField.new("Port", "itlc.port", ftypes.UINT32),
	ports = ProtoField.new("Ports", "itlc.ports", ftypes.UINT32),
	type = ProtoField.new("Client Type", "itlc.type", ftypes.STRING),
	ident = ProtoField.new("Client ID", "itlc.ident", ftypes.STRING),
	pcm = ProtoField.new("PCM Data", "itlc.pcm", ftypes.INT16),
	data = ProtoField.new("Unknown Data", "itlc.data", ftypes.BYTES),
}

local fieldarray = {}
for _, v in pairs(fields) do table.insert(fieldarray, v) end
itlc.fields = fieldarray

local commands = {
	[0] = "KA (keep alive)",
	[1] = "PING",
	[2] = "QUIT",
	[3] = "PLAY",
	[4] = "CAPS",
	[5] = "PCM",
}
setmetatable(commands, {__index = function(self, k) return "(Unknown command!)" end})

local subdis = {
	[0] = function(buffer, tree) end,  -- Nothing interesting...
	[1] = function(buffer, tree)
		tree:add(fields.pingdata, buffer())
	end,
	[2] = function(buffer, tree) end,  -- Nothing interesting...
	[3] = function(buffer, tree, pinfo)
		tree:add(fields.seconds, buffer(0, 4))
		tree:add(fields.microseconds, buffer(4, 4))
		local freq = buffer(8, 4):uint()
		local fr = tree:add(fields.frequency, buffer(8, 4))
		tree:add(fields.amplitude, buffer(12, 4))
		tree:add(fields.port, buffer(16, 4))
		local midi = 12 * math.log(freq / 440.0) / math.log(2) + 69
		fr:append_text(" [MIDI pitch approx. " .. midi .. "]")
		pinfo.cols.info = tostring(pinfo.cols.info) .. string.format(" freq=%d (MIDI %f) amp=%f dur=%f port=%d", freq, midi, buffer(12,4):float(), buffer(0, 4):uint() + 0.000001 * buffer(4, 4):uint(), buffer(16, 4):uint())
	end,
	[4] = function(buffer, tree, pinfo)
		local pt = tree:add(fields.ports, buffer(0, 4))
		if buffer(0,4):uint() == 0 then
			pt:append_text(" [probably a request from the broadcaster]")
			pinfo.cols.info = tostring(pinfo.cols.info) .. " [request]"
		else
			pinfo.cols.info = tostring(pinfo.cols.info) .. string.format(" type=%q uid=%q", buffer(4, 4):string(), buffer(8):string())
		end
		tree:add(fields.type, buffer(4, 4))
		tree:add(fields.ident, buffer(8))
	end,
	[5] = function(buffer, tree)
		tree:add(fields.pcm, buffer())
	end,
}
setmetatable(subdis, {__index = function(self, k) return function(buffer, tree)
	tree:add(fields.data, buffer())
end end})

function itlc.dissector(buffer, pinfo, tree)
	pinfo.cols.protocol = "ITLC"
	local st = tree:add(itlc, buffer(), "ITL Chorus Packet")
	local cmd = buffer(0,4):uint()
	st:add(fields.command, buffer(0,4), cmd, "Command: " .. commands[cmd] .. "(" .. cmd .. ")")
	pinfo.cols.info = commands[cmd]
	subdis[cmd](buffer(4):tvb(), st, pinfo)
end

local udp = DissectorTable.get("udp.port")
udp:add(13676, itlc)
udp:add(13677, itlc)

print('ITLC dissector loaded!')
