# A simple client that generates sine waves via python-pyaudio

import signal
import pyaudio
import sys
import socket
import time
import math
import struct
import socket
import optparse

from packet import Packet, CMD, stoi

parser = optparse.OptionParser()
parser.add_option('-t', '--test', dest='test', action='store_true', help='Play a test sequence (440,<rest>,880,440), then exit')
parser.add_option('-g', '--generator', dest='generator', default='math.sin', help='Set the generator (to a Python expression)')
parser.add_option('-u', '--uid', dest='uid', default='', help='Set the UID (identifier) of this client in the network')
parser.add_option('-p', '--port', dest='port', type='int', default=13676, help='Set the port to listen on')
parser.add_option('-r', '--rate', dest='rate', type='int', default=44100, help='Set the sample rate of the audio device')

options, args = parser.parse_args()

PORT = options.port
STREAMS = 1
IDENT = 'TONE'
UID = options.uid

LAST_SAMP = 0
FREQ = 0
PHASE = 0
RATE = options.rate
FPB = 64

Z_SAMP = '\x00\x00\x00\x00'
MAX = 0x7fffffff
AMP = MAX
MIN = -0x80000000

def lin_interp(frm, to, p):
    return p*to + (1-p)*frm

# Generator functions--should be cyclic within [0, 2*math.pi) and return [-1, 1]

def tri_wave(theta):
    if theta < math.pi/2:
        return lin_interp(0, 1, theta/(math.pi/2))
    elif theta < 3*math.pi/2:
        return lin_interp(1, -1, (theta-math.pi/2)/math.pi)
    else:
        return lin_interp(-1, 0, (theta-3*math.pi/2)/(math.pi/2))

def square_wave(theta):
    if theta < math.pi:
        return 1
    else:
        return -1

#generator = math.sin
#generator = tri_wave
#generator = square_wave
generator = eval(options.generator)

def sigalrm(sig, frm):
    global FREQ
    FREQ = 0

def lin_seq(frm, to, cnt):
    step = (to-frm)/float(cnt)
    samps = [0]*cnt
    for i in xrange(cnt):
        p = i / float(cnt-1)
        samps[i] = int(lin_interp(frm, to, p))
    return samps

def samps(freq, phase, cnt):
    global RATE, AMP
    samps = [0]*cnt
    for i in xrange(cnt):
        samps[i] = int(AMP * generator((phase + 2 * math.pi * freq * i / RATE) % (2*math.pi)))
    return samps, (phase + 2 * math.pi * freq * cnt / RATE) % (2*math.pi)

def to_data(samps):
    return struct.pack('i'*len(samps), *samps)

def gen_data(data, frames, time, status):
    global FREQ, PHASE, Z_SAMP, LAST_SAMP
    if FREQ == 0:
        PHASE = 0
        if LAST_SAMP == 0:
            return (Z_SAMP*frames, pyaudio.paContinue)
        fdata = lin_seq(LAST_SAMP, 0, frames)
        LAST_SAMP = fdata[-1]
        return (to_data(fdata), pyaudio.paContinue)
    fdata, PHASE = samps(FREQ, PHASE, frames)
    LAST_SAMP = fdata[-1]
    return (to_data(fdata), pyaudio.paContinue)

pa = pyaudio.PyAudio()
stream = pa.open(rate=RATE, channels=1, format=pyaudio.paInt32, output=True, frames_per_buffer=FPB, stream_callback=gen_data)

if options.test:
    FREQ = 440
    time.sleep(1)
    FREQ = 0
    time.sleep(1)
    FREQ = 880
    time.sleep(1)
    FREQ = 440
    time.sleep(2)
    exit()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', PORT))

signal.signal(signal.SIGALRM, sigalrm)

while True:
    data = ''
    while not data:
        try:
            data, cli = sock.recvfrom(4096)
        except socket.error:
            pass
    pkt = Packet.FromStr(data)
    print 'From', cli, 'command', pkt.cmd
    if pkt.cmd == CMD.KA:
        pass
    elif pkt.cmd == CMD.PING:
        sock.sendto(data, cli)
    elif pkt.cmd == CMD.QUIT:
        break
    elif pkt.cmd == CMD.PLAY:
        dur = pkt.data[0]+pkt.data[1]/1000000.0
        FREQ = pkt.data[2]
        AMP = MAX * (pkt.data[3]/255.0)
        signal.setitimer(signal.ITIMER_REAL, dur)
    elif pkt.cmd == CMD.CAPS:
        data = [0] * 8
        data[0] = STREAMS
        data[1] = stoi(IDENT)
        for i in xrange(len(UID)/4):
            data[i+2] = stoi(UID[4*i:4*(i+1)])
        sock.sendto(str(Packet(CMD.CAPS, *data)), cli)
    else:
        print 'Unknown cmd', pkt.cmd
