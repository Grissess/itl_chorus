from xml.etree import ElementTree as ET
import optparse, random, math, sys

def store_tup(opt, optstr, val, parser, nm, idx, filt=float):
    tup = getattr(parser.values, nm)
    setattr(parser.values, nm, tup[:idx] + (filt(val),) + tup[(idx+1):])

fund = 440.0
def to_freq(p):
    return fund * 2.0**((p - 69) / 12.0)

def to_pitch(f):
    try:
        return 12 * math.log(f / fund, 2) + 69
    except ValueError:
        print 'bad frequency', f
        raise

def store_target(opt, optstr, val, parser):
    print 'opt', opt, 'optstr', optstr, 'val', val, 'parser', parser
    if val.startswith('@'):
        val = int(val[1:])
    else:
        val = int(to_freq(float(val)))
    parser.values.targets.append((
        parser.values.voices,
        val,
        parser.values.fadeint,
        parser.values.inita,
        parser.values.randt,
        parser.values.randf,
        parser.values.fstep,
        parser.values.fina,
        parser.values.sweept,
        parser.values.fadeoutt
    ))

parser = optparse.OptionParser()
parser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Be verbose')
parser.add_option('-V', '--voices', dest='voices', type='int', help='Subsequent -t will have this many voices directed toward it')
parser.add_option('--fadeinlow', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('fadeint', 0), help='Low fade-in time for subsequent -t')
parser.add_option('--fadeinhigh', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('fadeint', 1), help='High fade-in time for subsequent -t')
parser.add_option('--initalow', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('inita', 0), help='Low init amplitude time for subsequent -t')
parser.add_option('--initahigh', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('inita', 1), help='High init amplitude time for subsequent -t')
parser.add_option('--randtlow', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('randt', 0), help='Low random time for subsequent -t')
parser.add_option('--randthigh', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('randf', 1), help='High random time for subsequent -t')
parser.add_option('--randflow', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('randf', 0), help='Low random freq for subsequent -t')
parser.add_option('--randfhigh', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('randt', 1), help='High random freq for subsequent -t')
parser.add_option('--fstep', dest='fstep', type='float', help='Frequency to wander by in random phase')
parser.add_option('--finalow', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('fina', 0), help='Low init amplitude time for subsequent -t')
parser.add_option('--finahigh', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('fina', 1), help='High init amplitude time for subsequent -t')
parser.add_option('--sweeplow', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('sweept', 0), help='Low sweep time for subsequent -t')
parser.add_option('--sweephigh', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('sweept', 1), help='High sweep time for subsequent -t')
parser.add_option('--fadeoutlow', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('fadeoutt', 0), help='Low fade-out time for subsequent -t')
parser.add_option('--fadeouthigh', action='callback', nargs=1, type='float', callback=store_tup, callback_args=('fadeoutt', 1), help='High fade-out time for subsequent -t')
parser.add_option('-t', '--target', action='callback', type='str', callback=store_target, nargs=1, help='Have some voices target this MIDI pitch or @frequency')
parser.add_option('-C', '--clear-targets', action='store_const', const=[], dest='targets', help='Clear all targets (including built in ones) prior')
parser.add_option('-r', '--resolution', dest='resolution', type='float', help='Period of generated samples')
parser.add_option('-c', '--chorus', dest='chorus', type='float', help='Random variation of frequency (factor)')
parser.add_option('--smooth', dest='smooth', type='int', help='Number of random uniform samples to perform to smooth')
parser.add_option('-D', '--duration', dest='duration', type='float', help='Length of the note')
parser.add_option('--slack', dest='slack', type='float', help='Slack added to duration to overcommit clients')
parser.add_option('--fundamental', dest='fundamental', type='float', help='Frequency of the A above middle C (traditionally 440 Hz)')

fadeint = (4.0, 6.0)
inita = (0.1, 0.2)
randt = (8.5, 9.0)
fina = (0.95, 1.0)
sweept = (17.5, 19.0)
fadeoutt = (1.5, 3.5)
randf = (200, 400)
fstep = 5
parser.set_defaults(
    resolution = 0.05,
    chorus = 0.02,
    smooth = 5,
    duration = 30.0,
    slack = 0.02,
    fundamental = 430.0,
    voices = 1,
    fadeint = fadeint,
    inita = inita,
    randt = randt,
    fina = fina,
    sweept = sweept,
    fadeoutt = fadeoutt,
    randf = randf,
    fstep = fstep,
    targets = [
        (2, to_freq(26), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (2, to_freq(38), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (3, to_freq(45), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (3, to_freq(50), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (3, to_freq(57), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (3, to_freq(62), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (3, to_freq(69), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (3, to_freq(74), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (3, to_freq(81), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (3, to_freq(86), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        (3, to_freq(90), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt), # Moorer claims this is here, but I'm not sure I believe him
        # Below this is the "shit note"
        #(2, to_freq(34), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(2, to_freq(35), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(2, to_freq(36), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(2, to_freq(42), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(47), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(48), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(54), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(59), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(60), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(66), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(72), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(77), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(83), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(84), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(85), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
        #(3, to_freq(90), fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt),
    ],
)
options, args = parser.parse_args()
fund = options.fundamental

smooth_rand_buf = [random.random() for i in range(options.smooth)]
def smooth_rand():
    global smooth_rand_buf
    rv = sum(smooth_rand_buf) / options.smooth
    smooth_rand_buf = [random.random()] + smooth_rand_buf[:-1]
    return rv

def smooth_uniform(a, b):
    return a + (b-a) * smooth_rand()

def clamp(u, l, h):
    return min((h, max((l, u))))

iv = ET.Element('iv')
ivmeta = ET.SubElement(iv, 'meta')
ivstreams = ET.SubElement(iv, 'streams')

for nvoice, freq, fadeint, inita, randt, randf, fstep, fina, sweept, fadeoutt in options.targets:
    for vn in range(nvoice):
        ivstream = ET.SubElement(ivstreams, 'stream', type='ns')
        vfadeint = random.uniform(*fadeint)
        vinita = random.uniform(*inita)
        vrandt = random.uniform(*randt)
        vfina = random.uniform(*fina)
        vsweept = random.uniform(*sweept)
        vfadeoutt = random.uniform(*fadeoutt)
        lastf = smooth_uniform(*randf)
        if options.verbose:
            print '-- setup:', freq, vn, 'fadeint', vfadeint, 'inita', vinita, 'randt', vrandt, 'fina', vfina, 'sweept', vsweept, 'fadeoutt', vfadeoutt, 'lastf', lastf
        cntr = 0
        for ts in range(int(options.duration / options.resolution)):
            tm = ts * options.resolution

            if tm < vfadeint:
                a = vinita * (tm / vfadeint)
                ap = 'fadein'
            elif tm < vrandt:
                a = vinita
                ap = 'inita'
            elif tm < vsweept:
                u = (clamp((tm - vfadeint - vrandt) / (vsweept - vfadeint - vrandt), 0.0, 1.0)) ** 2
                a = u * vfina + (1 - u) * vinita
                ap = 'sweep'
            else:
                a = vfina
                ap = 'fina'
            if tm > options.duration - vfadeoutt:
                a = vfina * max((((options.duration - tm) / vfadeoutt), 0))
                ap = 'fadeout'

            if tm < vfadeint + vrandt:
                lastf = clamp(lastf + smooth_uniform(-fstep, fstep), randf[0], randf[1])
                f = lastf
                fp = 'rand'
            elif tm < vsweept:
                u = clamp((tm - vfadeint - vrandt) / (vsweept - vfadeint - vrandt), 0.0, 1.0)
                f = u * freq + (1 - u) * lastf
                fp = 'sweep'
            else:
                f = freq * (1.0 + smooth_uniform(-options.chorus, options.chorus))
                fp = 'finf'

            if options.verbose:
                print freq, vn, tm, fp, f, ap, a

            ivnote = ET.SubElement(ivstream, 'note',
                id = str(cntr),
                pitch = str(to_pitch(f)),
                ampl = str(a),
                time = str(tm),
                dur = str(options.resolution + options.slack),
            )
            cntr += 1
            if cntr > 0:
                ivnote.set('par', '0')

sys.stdout.write(ET.tostring(iv, 'UTF-8'))
