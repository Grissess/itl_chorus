import socket
import sys
import struct
import time
import xml.etree.ElementTree as ET
import threading

PORT = 13676
if len(sys.argv) > 2:
	factor = float(sys.argv[2])
else:
	factor = 1

print 'Factor:', factor

class Packet(object):
	def __init__(self, cmd, *data):
		self.cmd = cmd
		self.data = data
		if len(data) >= 8:
			raise ValueError('Too many data')
		self.data = list(self.data) + [0] * (8-len(self.data))
	def __str__(self):
		return struct.pack('>L'+('L'*len(self.data)), self.cmd, *self.data)

class CMD:
	KA = 0 # No important data
	PING = 1 # Data are echoed exactly
	QUIT = 2 # No important data
	PLAY = 3 # seconds, microseconds, frequency (Hz), amplitude (0-255)

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

clients = []

s.sendto(str(Packet(CMD.PING)), ('255.255.255.255', PORT))
s.settimeout(0.5)

try:
	while True:
		data, src = s.recvfrom(4096)
		clients.append(src)
except socket.timeout:
	pass

print 'Clients:'
for cl in clients:
	print cl
	if sys.argv[1] == '-t':
		s.sendto(str(Packet(CMD.PLAY, 0, 250000, 440, 255)), cl)
		time.sleep(0.25)
		s.sendto(str(Packet(CMD.PLAY, 0, 250000, 880, 255)), cl)
	if sys.argv[1] == '-q':
		s.sendto(str(Packet(CMD.QUIT)), cl)

try:
	iv = ET.parse(sys.argv[1]).getroot()
except IOError:
	print 'Bad file'
	exit()

notestreams = iv.findall("./streams/stream[@type='ns']")

class NSThread(threading.Thread):
	def run(self):
		nsq, cl = self._Thread__args
		for note in nsq:
			ttime = float(note.get('time'))
			pitch = int(note.get('pitch'))
			vel = int(note.get('vel'))
			dur = factor*float(note.get('dur'))
			while time.time() - BASETIME < factor*ttime:
				time.sleep(factor*ttime - (time.time() - BASETIME))
			s.sendto(str(Packet(CMD.PLAY, int(dur), int((dur*1000000)%1000000), int(440.0 * 2**((pitch-69)/12.0)), vel*2)), cl)
			time.sleep(dur)

threads = []
for ns in notestreams:
	if not clients:
		print 'WARNING: Out of clients!'
		break
	nsq = ns.findall('note')
	threads.append(NSThread(args=(nsq, clients.pop(0))))

BASETIME = time.time()
for thr in threads:
	thr.start()
for thr in threads:
	thr.join()
