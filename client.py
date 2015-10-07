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
import array
import random

from packet import Packet, CMD, stoi

parser = optparse.OptionParser()
parser.add_option('-t', '--test', dest='test', action='store_true', help='Play a test sequence (440,<rest>,880,440), then exit')
parser.add_option('-g', '--generator', dest='generator', default='math.sin', help='Set the generator (to a Python expression)')
parser.add_option('--generators', dest='generators', action='store_true', help='Show the list of generators, then exit')
parser.add_option('-u', '--uid', dest='uid', default='', help='Set the UID (identifier) of this client in the network')
parser.add_option('-p', '--port', dest='port', type='int', default=13676, help='Set the port to listen on')
parser.add_option('-r', '--rate', dest='rate', type='int', default=44100, help='Set the sample rate of the audio device')
parser.add_option('-V', '--volume', dest='volume', type='float', default=1.0, help='Set the volume factor (>1 distorts, <1 attenuates)')

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

GENERATORS = [{'name': 'math.sin', 'args': None, 'desc': 'Sine function'},
        {'name':'math.cos', 'args': None, 'desc': 'Cosine function'}]

def generator(desc=None, args=None):
    def inner(f, desc=desc, args=args):
        if desc is None:
            desc = f.__doc__
        GENERATORS.append({'name': f.__name__, 'desc': desc, 'args': args})
        return f
    return inner

@generator('Simple triangle wave (peaks/troughs at pi/2, 3pi/2)')
def tri_wave(theta):
    if theta < math.pi/2:
        return lin_interp(0, 1, theta/(math.pi/2))
    elif theta < 3*math.pi/2:
        return lin_interp(1, -1, (theta-math.pi/2)/math.pi)
    else:
        return lin_interp(-1, 0, (theta-3*math.pi/2)/(math.pi/2))

@generator('Simple square wave (piecewise 1 at x<pi, 0 else)')
def square_wave(theta):
    if theta < math.pi:
        return 1
    else:
        return -1

@generator('Random (noise) generator')
def noise(theta):
    return random.random() * 2 - 1

@generator('File generator', '(<file>[, <bits=8>[, <signed=True>[, <0=linear interp (default), 1=nearest>[, <swapbytes=False>]]]])')
class file_samp(object):
    LINEAR = 0
    NEAREST = 1
    TYPES = {8: 'B', 16: 'H', 32: 'L'}
    def __init__(self, fname, bits=8, signed=True, samp=LINEAR, swab=False):
        tp = self.TYPES[bits]
        if signed:
            tp = tp.lower()
        self.max = float((2 << bits) - 1)
        self.buffer = array.array(tp)
        self.buffer.fromstring(open(fname, 'rb').read())
        if swab:
            self.buffer.byteswap()
        self.samp = samp
    def __call__(self, theta):
        norm = theta / (2*math.pi)
        if self.samp == self.LINEAR:
            v = norm*len(self.buffer)
            l = int(math.floor(v))
            h = int(math.ceil(v))
            if l == h:
                return self.buffer[l]/self.max
            if h >= len(self.buffer):
                h = 0
            return lin_interp(self.buffer[l], self.buffer[h], v-l)/self.max
        elif self.samp == self.NEAREST:
            return self.buffer[int(math.ceil(norm*len(self.buffer) - 0.5))]/self.max

@generator('Harmonics generator (adds overtones at f, 2f, 3f, 4f, etc.)', '(<generator>, <amplitude of f>, <amp 2f>, <amp 3f>, ...)')
class harmonic(object):
    def __init__(self, gen, *spectrum):
        self.gen = gen
        self.spectrum = spectrum
    def __call__(self, theta):
        return max(-1, min(1, sum([amp*self.gen((i+1)*theta % (2*math.pi)) for i, amp in enumerate(self.spectrum)])))

@generator('Mix generator', '(<generator>[, <amp>], [<generator>[, <amp>], [...]])')
class mixer(object):
    def __init__(self, *specs):
        self.pairs = []
        i = 0
        while i < len(specs):
            if i+1 < len(specs) and isinstance(specs[i+1], (float, int)):
                pair = (specs[i], specs[i+1])
                i += 2
            else:
                pair = (specs[i], None)
                i += 1
            self.pairs.append(pair)
        tamp = 1 - min(1, sum([amp for gen, amp in self.pairs if amp is not None]))
        parts = float(len([None for gen, amp in self.pairs if amp is None]))
        for idx, pair in enumerate(self.pairs):
            if pair[1] is None:
                self.pairs[idx] = (pair[0], tamp / parts)
    def __call__(self, theta):
        return max(-1, min(1, sum([amp*gen(theta) for gen, amp in self.pairs])))

@generator('Phase offset generator (in radians; use math.pi)', '(<generator>, <offset>)')
class phase_off(object):
    def __init__(self, gen, offset):
        self.gen = gen
        self.offset = offset
    def __call__(self, theta):
        return self.gen((theta + self.offset) % (2*math.pi))

if options.generators:
    for item in GENERATORS:
        print item['name'],
        if item['args'] is not None:
            print item['args'],
        print '--', item['desc']
    exit()

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
        samps[i] = int(AMP * max(-1, min(1, options.volume*generator((phase + 2 * math.pi * freq * i / RATE) % (2*math.pi)))))
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
