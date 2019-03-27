import pyaudio
import socket
import optparse
import tarfile
import wave
import cStringIO as StringIO
import array
import time
import colorsys

from packet import Packet, CMD, stoi, OBLIGATE_POLYPHONE

parser = optparse.OptionParser()
parser.add_option('-t', '--test', dest='test', action='store_true', help='As a test, play all samples then exit')
parser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Be verbose')
parser.add_option('-V', '--volume', dest='volume', type='float', default=1.0, help='Set the volume factor (nominally [0.0, 1.0], but >1.0 can be used to amplify with possible distortion)')
parser.add_option('-r', '--rate', dest='rate', type='int', default=44100, help='Audio sample rate for output and of input files')
parser.add_option('-u', '--uid', dest='uid', default='', help='User identifier of this client')
parser.add_option('-p', '--port', dest='port', default=13677, type='int', help='UDP port to listen on')
parser.add_option('-c', '--clamp', dest='clamp', action='store_true', help='Clamp over-the-wire amplitudes to 0.0-1.0')
parser.add_option('--amp-exp', dest='amp_exp', default=2.0, type='float', help='Raise floating amplitude to this power before computing raw amplitude')
parser.add_option('--repeat', dest='repeat', action='store_true', help='If a note plays longer than a sample length, keep playing the sample')
parser.add_option('--cut', dest='cut', action='store_true', help='If a note ends within a sample, stop playing that sample immediately')
parser.add_option('-n', '--max-voices', dest='max_voices', default=-1, type='int', help='Only support this many notes playing simultaneously (earlier ones get dropped)')
parser.add_option('--pg-low-freq', dest='low_freq', type='int', default=40, help='Low frequency for colored background')
parser.add_option('--pg-high-freq', dest='high_freq', type='int', default=1500, help='High frequency for colored background')
parser.add_option('--pg-log-base', dest='log_base', type='int', default=2, help='Logarithmic base for coloring (0 to make linear)')
parser.add_option('--counter-modulus', dest='counter_modulus', type='int', default=16, help='Number of packet events in period of the terminal color scroll on the left margin')

options, args = parser.parse_args()

MAX = 0x7fffffff
MIN = -0x80000000
IDENT = 'DRUM'

if not args:
    print 'Need at least one drumpack (.tar.bz2) as an argument!'
    parser.print_usage()
    exit(1)

def rgb_for_freq_amp(f, a):
    pitchval = float(f - options.low_freq) / (options.high_freq - options.low_freq)
    a = max((min((a, 1.0)), 0.0))
    if options.log_base == 0:
        try:
            pitchval = math.log(pitchval) / math.log(options.log_base)
        except ValueError:
            pass
    bgcol = colorsys.hls_to_rgb(min((1.0, max((0.0, pitchval)))), 0.5 * (a ** 2), 1.0)
    return [int(i*255) for i in bgcol]

DRUMS = {}

for fname in args:
    print 'Reading', fname, '...'
    tf = tarfile.open(fname, 'r')
    names = tf.getnames()
    for nm in names:
        if not (nm.endswith('.wav') or nm.endswith('.raw')) or len(nm) < 5:
            continue
        frq = int(nm[:-4])
        if options.verbose:
            print '\tLoading frq', frq, '...'
        fo = tf.extractfile(nm)
        if nm.endswith('.wav'):
            wf = wave.open(fo)
            if wf.getnchannels() != 1:
                print '\t\tWARNING: Channel count wrong: got', wf.getnchannels(), 'expecting 1'
            if wf.getsampwidth() != 4:
                print '\t\tWARNING: Sample width wrong: got', wf.getsampwidth(), 'expecting 4'
            if wf.getframerate() != options.rate:
                print '\t\tWARNING: Rate wrong: got', wf.getframerate(), 'expecting', options.rate, '(maybe try setting -r?)'
            frames = wf.getnframes()
            data = ''
            while len(data) < wf.getsampwidth() * frames:
                data += wf.readframes(frames - len(data) / wf.getsampwidth())
        elif nm.endswith('.raw'):
            data = fo.read()
            frames = len(data) / 4
        if options.verbose:
            print '\t\tData:', frames, 'samples,', len(data), 'bytes'
        if frq in DRUMS:
            print '\t\tWARNING: frequency', frq, 'already in map, overwriting...'
        DRUMS[frq] = data

if options.verbose:
    print len(DRUMS), 'sounds loaded'

PLAYING = []

class SampleReader(object):
    def __init__(self, buf, total, amp):
        self.buf = buf
        self.total = total
        self.cur = 0
        self.amp = amp

    def read(self, bytes):
        if self.cur >= self.total:
            return ''
        res = ''
        while self.cur < self.total and len(res) < bytes:
            data = self.buf[self.cur % len(self.buf):self.cur % len(self.buf) + bytes - len(res)]
            self.cur += len(data)
            res += data
        arr = array.array('i')
        arr.fromstring(res)
        for i in range(len(arr)):
            arr[i] = int(arr[i] * self.amp)
        return arr.tostring()

    def __repr__(self):
        return '<SR (%d) @%d / %d A:%f>'%(len(self.buf), self.cur, self.total, self.amp)

def gen_data(data, frames, tm, status):
    fdata = array.array('l', [0] * frames)
    torem = set()
    for src in set(PLAYING):
        buf = src.read(frames * 4)
        if not buf:
            torem.add(src)
            continue
        samps = array.array('i')
        samps.fromstring(buf)
        if len(samps) < frames:
            samps.extend([0] * (frames - len(samps)))
        for i in range(frames):
            fdata[i] += samps[i]
    for src in torem:
        PLAYING.remove(src)
    for i in range(frames):
        fdata[i] = max(MIN, min(MAX, fdata[i]))
    fdata = array.array('i', fdata)
    return (fdata.tostring(), pyaudio.paContinue)

pa = pyaudio.PyAudio()
stream = pa.open(rate=options.rate, channels=1, format=pyaudio.paInt32, output=True, frames_per_buffer=64, stream_callback=gen_data)

if options.test:
    for frq in sorted(DRUMS.keys()):
        print 'Current playing:', PLAYING
        print 'Playing:', frq
        data = DRUMS[frq]
        PLAYING.append(SampleReader(data, len(data), options.volume))
        time.sleep(len(data) / (4.0 * options.rate))
    print 'Done'
    exit()


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', options.port))

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
        frq = pkt.data[2]
        if frq not in DRUMS:
            print 'WARNING: No such instrument', frq, ', ignoring...'
            continue
        rdata = DRUMS[frq]
        rframes = len(rdata) / 4
        dur = pkt.data[0]+pkt.data[1]/1000000.0
        dframes = int(dur * options.rate)
        if not options.repeat:
            dframes = max(dframes, rframes)
        if not options.cut:
            dframes = rframes * ((dframes + rframes - 1) / rframes)
        amp = options.volume * pkt.as_float(3)
        if options.clamp:
            amp = max(min(amp, 1.0), 0.0)
        PLAYING.append(SampleReader(rdata, dframes * 4, amp**options.amp_exp))
        if options.max_voices >= 0:
            while len(PLAYING) > options.max_voices:
                PLAYING.pop(0)
        frgb = rgb_for_freq_amp(pkt.data[2], pkt.as_float(3))
        print '\x1b[1;32mPLAY',
        print '\x1b[1;34mVOICE', '{:03}'.format(pkt.data[4]),
        print '\x1b[1;38;2;{};{};{}mFREQ'.format(*frgb), '{:04}'.format(pkt.data[2]), 'AMP', '%08.6f'%pkt.as_float(3),
        if pkt.data[0] == 0 and pkt.data[1] == 0:
            print '\x1b[1;35mSTOP!!!'
        else:
            print '\x1b[1;36mDUR', '%08.6f'%dur
        #signal.setitimer(signal.ITIMER_REAL, dur)
    elif pkt.cmd == CMD.CAPS:
        data = [0] * 8
        data[0] = OBLIGATE_POLYPHONE
        data[1] = stoi(IDENT)
        for i in xrange(len(options.uid)/4 + 1):
            data[i+2] = stoi(options.uid[4*i:4*(i+1)])
        sock.sendto(str(Packet(CMD.CAPS, *data)), cli)
        print '\x1b[1;34mCAPS'
#    elif pkt.cmd == CMD.PCM:
#        fdata = data[4:]
#        fdata = struct.pack('16i', *[i<<16 for i in struct.unpack('16h', fdata)])
#        QUEUED_PCM += fdata
#        print 'Now', len(QUEUED_PCM) / 4.0, 'frames queued'
    else:
        print 'Unknown cmd', pkt.cmd
