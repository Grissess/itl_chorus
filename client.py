# A simple client that generates sine waves via python-pyaudio

import signal
import pyaudio
import sys
import socket
import time
import math
import struct
import socket

from packet import Packet, CMD, stoi

PORT = 13676
STREAMS = 1
IDENT = 'TONE'
if len(sys.argv) > 1:
    UID = sys.argv[1].rfill(24, '\x00')
else:
    UID = '\x00'*24

LAST_SAMP = 0
FREQ = 0
PHASE = 0
RATE = 44100
FPB = 64

Z_SAMP = '\x00\x00\x00\x00'
MAX = 0x7fffffff
AMP = MAX
MIN = -0x80000000

def sigalrm(sig, frm):
    global FREQ
    FREQ = 0

def lin_interp(frm, to, cnt):
    step = (to-frm)/float(cnt)
    samps = [0]*cnt
    for i in xrange(cnt):
        p = i / float(cnt-1)
        samps[i] = int(p*to + (1-p)*frm)
    return samps

def sine(freq, phase, cnt):
    global RATE, AMP
    samps = [0]*cnt
    for i in xrange(cnt):
        samps[i] = int(AMP * math.sin(phase + 2 * math.pi * freq * i / RATE))
    return samps, phase + 2 * math.pi * freq * cnt / RATE

def to_data(samps):
    return struct.pack('i'*len(samps), *samps)

def gen_data(data, frames, time, status):
    global FREQ, PHASE, Z_SAMP, LAST_SAMP
    if FREQ == 0:
        PHASE = 0
        if LAST_SAMP == 0:
            return (Z_SAMP*frames, pyaudio.paContinue)
        fdata = lin_interp(LAST_SAMP, 0, frames)
        LAST_SAMP = fdata[-1]
        return (to_data(fdata), pyaudio.paContinue)
    fdata, PHASE = sine(FREQ, PHASE, frames)
    LAST_SAMP = fdata[-1]
    return (to_data(fdata), pyaudio.paContinue)

pa = pyaudio.PyAudio()
stream = pa.open(rate=RATE, channels=1, format=pyaudio.paInt32, output=True, frames_per_buffer=FPB, stream_callback=gen_data)

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
