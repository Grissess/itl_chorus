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
import threading
import thread
import colorsys

from packet import Packet, CMD, stoi

parser = optparse.OptionParser()
parser.add_option('-t', '--test', dest='test', action='store_true', help='Play a test sequence (440,<rest>,880,440), then exit')
parser.add_option('-g', '--generator', dest='generator', default='math.sin', help='Set the generator (to a Python expression)')
parser.add_option('--generators', dest='generators', action='store_true', help='Show the list of generators, then exit')
parser.add_option('-u', '--uid', dest='uid', default='', help='Set the UID (identifier) of this client in the network')
parser.add_option('-p', '--port', dest='port', type='int', default=13676, help='Set the port to listen on')
parser.add_option('-r', '--rate', dest='rate', type='int', default=44100, help='Set the sample rate of the audio device')
parser.add_option('-V', '--volume', dest='volume', type='float', default=1.0, help='Set the volume factor (>1 distorts, <1 attenuates)')
parser.add_option('-n', '--streams', dest='streams', type='int', default=1, help='Set the number of streams this client will play back')
parser.add_option('-N', '--numpy', dest='numpy', action='store_true', help='Use numpy acceleration')
parser.add_option('-G', '--gui', dest='gui', default='', help='set a GUI to use')
parser.add_option('--pg-fullscreen', dest='fullscreen', action='store_true', help='Use a full-screen video mode')
parser.add_option('--pg-samp-width', dest='samp_width', type='int', help='Set the width of the sample pane (by default display width / 2)')
parser.add_option('--pg-bgr-width', dest='bgr_width', type='int', help='Set the width of the bargraph pane (by default display width / 2)')
parser.add_option('--pg-height', dest='height', type='int', help='Set the height of the window or full-screen video mode')
parser.add_option('--pg-no-colback', dest='no_colback', action='store_true', help='Don\'t render a colored background')
parser.add_option('--pg-low-freq', dest='low_freq', type='int', default=40, help='Low frequency for colored background')
parser.add_option('--pg-high-freq', dest='high_freq', type='int', default=1500, help='High frequency for colored background')
parser.add_option('--pg-log-base', dest='log_base', type='int', default=2, help='Logarithmic base for coloring (0 to make linear)')
parser.add_option('--counter-modulus', dest='counter_modulus', type='int', default=16, help='Number of packet events in period of the terminal color scroll on the left margin')
parser.add_option('--pcm-corr-rate', dest='pcm_corr_rate', type='float', default=0.05, help='Amount of time to correct buffer drift, measured as percentage of the current sync rate')

options, args = parser.parse_args()

if options.numpy:
    import numpy

PORT = options.port
STREAMS = options.streams
IDENT = 'TONE'
UID = options.uid

LAST_SAMPS = [0] * STREAMS
LAST_SAMPLES = []
FREQS = [0] * STREAMS
PHASES = [0] * STREAMS
RATE = options.rate
FPB = 64

Z_SAMP = '\x00\x00\x00\x00'
MAX = 0x7fffffff
AMPS = [MAX] * STREAMS
MIN = -0x80000000

EXPIRATIONS = [0] * STREAMS
QUEUED_PCM = ''
DRIFT_FACTOR = 1.0
DRIFT_ERROR = 0.0
LAST_SYN = None

def lin_interp(frm, to, p):
    return p*to + (1-p)*frm

def rgb_for_freq_amp(f, a):
    a = max((min((a, 1.0)), 0.0))
    pitchval = float(f - options.low_freq) / (options.high_freq - options.low_freq)
    if options.log_base == 0:
        try:
            pitchval = math.log(pitchval) / math.log(options.log_base)
        except ValueError:
            pass
    bgcol = colorsys.hls_to_rgb(min((1.0, max((0.0, pitchval)))), 0.5 * (a ** 2), 1.0)
    return [int(i*255) for i in bgcol]

# GUIs

GUIs = {}

def GUI(f):
    GUIs[f.__name__] = f
    return f

@GUI
def pygame_notes():
    import pygame
    import pygame.gfxdraw
    pygame.init()

    dispinfo = pygame.display.Info()
    DISP_WIDTH = 640
    DISP_HEIGHT = 480
    if dispinfo.current_h > 0 and dispinfo.current_w > 0:
        DISP_WIDTH = dispinfo.current_w
        DISP_HEIGHT = dispinfo.current_h

    SAMP_WIDTH = DISP_WIDTH / 2
    if options.samp_width > 0:
        SAMP_WIDTH = options.samp_width
    BGR_WIDTH = DISP_WIDTH / 2
    if options.bgr_width > 0:
        BGR_WIDTH = options.bgr_width
    HEIGHT = DISP_HEIGHT
    if options.height > 0:
        HEIGHT = options.height

    flags = 0
    if options.fullscreen:
        flags |= pygame.FULLSCREEN

    disp = pygame.display.set_mode((SAMP_WIDTH + BGR_WIDTH, HEIGHT), flags)

    WIDTH, HEIGHT = disp.get_size()
    SAMP_WIDTH = WIDTH / 2
    BGR_WIDTH = WIDTH - SAMP_WIDTH
    PFAC = HEIGHT / 128.0

    sampwin = pygame.Surface((SAMP_WIDTH, HEIGHT))
    sampwin.set_colorkey((0, 0, 0))
    lastsy = HEIGHT / 2
    bgrwin = pygame.Surface((BGR_WIDTH, HEIGHT))
    bgrwin.set_colorkey((0, 0, 0))

    clock = pygame.time.Clock()
    font = pygame.font.SysFont(pygame.font.get_default_font(), 24)

    while True:
        if options.no_colback:
            disp.fill((0, 0, 0), (0, 0, WIDTH, HEIGHT))
        else:
            gap = WIDTH / STREAMS
            for i in xrange(STREAMS):
                FREQ = FREQS[i]
                AMP = AMPS[i]
                if FREQ > 0:
                    bgcol = rgb_for_freq_amp(FREQ, float(AMP) / MAX)
                else:
                    bgcol = (0, 0, 0)
                #print i, ':', pitchval
                disp.fill(bgcol, (i*gap, 0, gap, HEIGHT))

        bgrwin.scroll(-1, 0)
        bgrwin.fill((0, 0, 0), (BGR_WIDTH - 1, 0, 1, HEIGHT))
        for i in xrange(STREAMS):
            FREQ = FREQS[i]
            AMP = AMPS[i]
            if FREQ > 0:
                try:
                    pitch = 12 * math.log(FREQ / 440.0, 2) + 69
                except ValueError:
                    pitch = 0
            else:
                pitch = 0
            col = [int((AMP / MAX) * 255)] * 3
            bgrwin.fill(col, (BGR_WIDTH - 1, HEIGHT - pitch * PFAC - PFAC, 1, PFAC))

        sampwin.scroll(-len(LAST_SAMPLES), 0)
        x = max(0, SAMP_WIDTH - len(LAST_SAMPLES))
        sampwin.fill((0, 0, 0), (x, 0, SAMP_WIDTH - x, HEIGHT))
        for i in LAST_SAMPLES:
            sy = int((float(i) / MAX) * (HEIGHT / 2) + (HEIGHT / 2))
            pygame.gfxdraw.line(sampwin, x - 1, lastsy, x, sy, (0, 255, 0))
            x += 1
            lastsy = sy
        del LAST_SAMPLES[:]
        #w, h = SAMP_WIDTH, HEIGHT
        #pts = [(BGR_WIDTH, HEIGHT / 2), (w + BGR_WIDTH, HEIGHT / 2)]
        #x = w + BGR_WIDTH
        #for i in reversed(LAST_SAMPLES):
        #    pts.insert(1, (x, int((h / 2) + (float(i) / MAX) * (h / 2))))
        #    x -= 1
        #    if x < BGR_WIDTH:
        #        break
        #if len(pts) > 2:
        #    pygame.gfxdraw.aapolygon(disp, pts, [0, 255, 0])

        disp.blit(bgrwin, (0, 0))
        disp.blit(sampwin, (BGR_WIDTH, 0))
        if QUEUED_PCM:
            tsurf = font.render('%08.6f'%(DRIFT_FACTOR,), True, (255, 255, 255), (0, 0, 0))
            disp.fill((0, 0, 0), tsurf.get_rect())
            disp.blit(tsurf, (0, 0))
        pygame.display.flip()

        for ev in pygame.event.get():
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    thread.interrupt_main()
                    pygame.quit()
                    exit()
            elif ev.type == pygame.QUIT:
                thread.interrupt_main()
                pygame.quit()
                exit()

        clock.tick(60)

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

@generator('Saw wave (line from (0, 1) to (2pi, -1))')
def saw_wave(theta):
    return lin_interp(1, -1, theta/(math.pi * 2))

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

@generator('General harmonics generator (adds arbitrary overtones)', '(<generator>, <factor of f>, <amplitude>, <factor>, <amplitude>, ...)')
class genharmonic(object):
    def __init__(self, gen, *harmonics):
        self.gen = gen
        self.harmonics = zip(harmonics[::2], harmonics[1::2])
    def __call__(self, theta):
        return max(-1, min(1, sum([amp * self.gen(i * theta % (2*math.pi)) for i, amp in self.harmonics])))

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

#def sigalrm(sig, frm):
#    global FREQ
#    FREQ = 0

if options.numpy:
    def lin_seq(frm, to, cnt):
        return numpy.linspace(frm, to, cnt, dtype=numpy.int32)

    def samps(freq, amp, phase, cnt):
        samps = numpy.ndarray((cnt,), numpy.int32)
        pvel = 2 * math.pi * freq / RATE
        fac = options.volume * amp / float(STREAMS)
        for i in xrange(cnt):
            samps[i] = fac * max(-1, min(1, generator(phase)))
            phase = (phase + pvel) % (2 * math.pi)
        return samps, phase

    def to_data(samps):
        return samps.tobytes()

    def mix(a, b):
        return a + b

    def resample(samps, amt):
        samps = numpy.frombuffer(samps, numpy.int32)
        return numpy.interp(numpy.linspace(0, samps.shape[0], amt, False), numpy.linspace(0, samps.shape[0], samps.shape[0], False), samps).tobytes()

else:
    def lin_seq(frm, to, cnt):
        step = (to-frm)/float(cnt)
        samps = [0]*cnt
        for i in xrange(cnt):
            p = i / float(cnt-1)
            samps[i] = int(lin_interp(frm, to, p))
        return samps

    def samps(freq, amp, phase, cnt):
        global RATE
        samps = [0]*cnt
        for i in xrange(cnt):
            samps[i] = int(2*amp / float(STREAMS) * max(-1, min(1, options.volume*generator((phase + 2 * math.pi * freq * i / RATE) % (2*math.pi)))))
        return samps, (phase + 2 * math.pi * freq * cnt / RATE) % (2*math.pi)

    def to_data(samps):
        return struct.pack('i'*len(samps), *samps)

    def mix(a, b):
        return [min(MAX, max(MIN, i + j)) for i, j in zip(a, b)]

    def resample(samps, amt):
        isl = len(samps) / 4
        if isl == amt:
            return samps
        arr = struct.unpack(str(isl)+'i', samps)
        out = []
        for i in range(amt):
            effidx = i * (isl / amt)
            ieffidx = int(effidx)
            if ieffidx == effidx:
                out.append(arr[ieffidx])
            else:
                frac = effidx - ieffidx
                out.append(arr[ieffidx] * (1-frac) + arr[ieffidx+1] * frac)
        return struct.pack(str(amt)+'i', *out)

def gen_data(data, frames, tm, status):
    global FREQS, PHASE, Z_SAMP, LAST_SAMP, LAST_SAMPLES, QUEUED_PCM, DRIFT_FACTOR, DRIFT_ERROR
    if len(QUEUED_PCM) >= frames*4:
        desired_frames = DRIFT_FACTOR * frames
        err_frames = desired_frames - int(desired_frames)
        desired_frames = int(desired_frames)
        DRIFT_ERROR += err_frames
        if DRIFT_ERROR >= 1.0:
            desired_frames += 1
            DRIFT_ERROR -= 1.0
        fdata = QUEUED_PCM[:desired_frames*4]
        QUEUED_PCM = QUEUED_PCM[desired_frames*4:]
        if options.gui:
            LAST_SAMPLES.extend(struct.unpack(str(desired_frames)+'i', fdata))
        return resample(fdata, frames), pyaudio.paContinue
    if options.numpy:
        fdata = numpy.zeros((frames,), numpy.int32)
    else:
        fdata = [0] * frames
    for i in range(STREAMS):
        FREQ = FREQS[i]
        LAST_SAMP = LAST_SAMPS[i]
        AMP = AMPS[i]
        EXPIRATION = EXPIRATIONS[i]
        PHASE = PHASES[i]
        if FREQ != 0:
            if time.time() > EXPIRATION:
                FREQ = 0
                FREQS[i] = 0
        if FREQ == 0:
            PHASES[i] = 0
            if LAST_SAMP != 0:
                vdata = lin_seq(LAST_SAMP, 0, frames)
                fdata = mix(fdata, vdata)
                LAST_SAMPS[i] = vdata[-1]
        else:
            vdata, PHASE = samps(FREQ, AMP, PHASE, frames)
            fdata = mix(fdata, vdata)
            PHASES[i] = PHASE
            LAST_SAMPS[i] = vdata[-1]
    if options.gui:
        LAST_SAMPLES.extend(fdata)
    return (to_data(fdata), pyaudio.paContinue)

pa = pyaudio.PyAudio()
stream = pa.open(rate=RATE, channels=1, format=pyaudio.paInt32, output=True, frames_per_buffer=FPB, stream_callback=gen_data)

if options.gui:
    guithread = threading.Thread(target=GUIs[options.gui])
    guithread.setDaemon(True)
    guithread.start()

if options.test:
    FREQS[0] = 440
    EXPIRATIONS[0] = time.time() + 1
    time.sleep(1)
    FREQS[0] = 0
    time.sleep(1)
    FREQS[0] = 880
    EXPIRATIONS[0] = time.time() + 1
    time.sleep(1)
    FREQS[0] = 440
    EXPIRATIONS[0] = time.time() + 2
    time.sleep(2)
    exit()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', PORT))

#signal.signal(signal.SIGALRM, sigalrm)

counter = 0
while True:
    data = ''
    while not data:
        try:
            data, cli = sock.recvfrom(4096)
        except socket.error:
            pass
    pkt = Packet.FromStr(data)
    if pkt.cmd != CMD.PCM:
        crgb = [int(i*255) for i in colorsys.hls_to_rgb((float(counter) / options.counter_modulus) % 1.0, 0.5, 1.0)]
        print '\x1b[38;2;{};{};{}m#'.format(*crgb),
        counter += 1
        print '\x1b[mFrom', cli, 'command', pkt.cmd,
    if pkt.cmd == CMD.KA:
        print '\x1b[37mKA'
    elif pkt.cmd == CMD.PING:
        sock.sendto(data, cli)
        print '\x1b[1;33mPING'
    elif pkt.cmd == CMD.QUIT:
        print '\x1b[1;31mQUIT'
        break
    elif pkt.cmd == CMD.PLAY:
        voice = pkt.data[4]
        dur = pkt.data[0]+pkt.data[1]/1000000.0
        FREQS[voice] = pkt.data[2]
        AMPS[voice] = MAX * max(min(pkt.as_float(3), 1.0), 0.0)
        EXPIRATIONS[voice] = time.time() + dur
        vrgb = [int(i*255) for i in colorsys.hls_to_rgb(float(voice) / STREAMS * 2.0 / 3.0, 0.5, 1.0)]
        frgb = rgb_for_freq_amp(pkt.data[2], pkt.as_float(3))
        print '\x1b[1;32mPLAY',
        print '\x1b[1;38;2;{};{};{}mVOICE'.format(*vrgb), '{:03}'.format(voice),
        print '\x1b[1;38;2;{};{};{}mFREQ'.format(*frgb), '{:04}'.format(pkt.data[2]), 'AMP', '%08.6f'%pkt.as_float(3),
        if pkt.data[0] == 0 and pkt.data[1] == 0:
            print '\x1b[1;35mSTOP!!!'
        else:
            print '\x1b[1;36mDUR', '%08.6f'%dur
        #signal.setitimer(signal.ITIMER_REAL, dur)
    elif pkt.cmd == CMD.CAPS:
        data = [0] * 8
        data[0] = STREAMS
        data[1] = stoi(IDENT)
        for i in xrange(len(UID)/4 + 1):
            data[i+2] = stoi(UID[4*i:4*(i+1)])
        sock.sendto(str(Packet(CMD.CAPS, *data)), cli)
        print '\x1b[1;34mCAPS'
    elif pkt.cmd == CMD.PCM:
        fdata = data[4:]
        fdata = struct.pack('16i', *[i<<16 for i in struct.unpack('16h', fdata)])
        QUEUED_PCM += fdata
        #print 'Now', len(QUEUED_PCM) / 4.0, 'frames queued'
    elif pkt.cmd == CMD.PCMSYN:
        print '\x1b[1;37mPCMSYN',
        bufamt = pkt.data[0]
        print '\x1b[0m DESBUF={}'.format(bufamt),
        if LAST_SYN is None:
            LAST_SYN = time.time()
        else:
            dt = time.time() - LAST_SYN
            dfr = dt * RATE
            bufnow = len(QUEUED_PCM) / 4
            print '\x1b[35m CURBUF={}'.format(bufnow),
            if bufnow != 0:
                DRIFT_FACTOR = 1.0 + float(bufnow - bufamt) / (bufamt * dfr * options.pcm_corr_rate)
                print '\x1b[37m (DRIFT_FACTOR=%08.6f)'%(DRIFT_FACTOR,),
            print
    else:
        print '\x1b[1;31mUnknown cmd', pkt.cmd
