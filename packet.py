#Simple packet type for the simple protocol

import struct

class Packet(object):
	def __init__(self, cmd, *data):
		self.cmd = cmd
		self.data = data
		if len(data) > 8:
			raise ValueError('Too many data')
		self.data = list(self.data) + [0] * (8-len(self.data))
        @classmethod
        def FromStr(cls, s):
            parts = struct.unpack('>9L', s)
            return cls(parts[0], *parts[1:])
        def as_float(self, i):
            return struct.unpack('>f', struct.pack('>L', self.data[i]))[0]
	def __str__(self):
		return struct.pack('>L'+(''.join('f' if isinstance(i, float) else 'L' for i in self.data)), self.cmd, *self.data)

class CMD:
	KA = 0 # No important data
	PING = 1 # Data are echoed exactly
	QUIT = 2 # No important data
	PLAY = 3 # seconds, microseconds, frequency (Hz), amplitude (0.0 - 1.0), port
        CAPS = 4 # ports, client type (1), user ident (2-7)
        PCM = 5 # 16 samples, encoded S16_LE

def itos(i):
    return struct.pack('>L', i)

def stoi(s):
    return struct.unpack('>L', s)[0]
