from xml.etree import ElementTree as ET
import optparse

parser = optparse.OptionParser()
parser.add_option('-t', '--tempo', dest='tempo', type='float', help='Tempo (in BPM)')
parser.add_option('-r', '--resolution', dest='resolution', type='float', help='Approximate resolution in seconds (overrides tempo)')
parser.add_option('-f', '--float', dest='float', action='store_true', help='Allow floating point representations on output')
parser.add_option('-T', '--transpose', dest='transpose', type='float', help='Transpose by this many semitones')
parser.set_defaults(tempo=60000, resolution=None, transpose=0)
options, args = parser.parse_args()

maybe_int = int
if options.float:
    maybe_int = float

class Note(object):
    def __init__(self, time, dur, pitch, ampl):
        self.time = time
        self.dur = dur
        self.pitch = pitch
        self.ampl = ampl

if options.resolution is not None:
    options.tempo = 60.0 / options.resolution

options.tempo = maybe_int(options.tempo)

def to_beats(tm):
    return options.tempo * tm / 60.0

for fname in args:
    try:
        iv = ET.parse(fname).getroot()
    except IOError:
        import traceback
        traceback.print_exc()
        print fname, ': Bad file'
        continue

    print options.tempo,

    ns = iv.find('./streams/stream[@type="ns"]')
    prevn = None
    for note in ns.findall('note'):
        n = Note(
            float(note.get('time')),
            float(note.get('dur')),
            float(note.get('pitch')) + options.transpose,
            float(note.get('ampl', float(note.get('vel', 127.0)) / 127.0)),
        )
        if prevn is not None:
            rtime = to_beats(n.time - (prevn.time + prevn.dur))
            if rtime >= 1:
                print 0, maybe_int(rtime),
            ntime = to_beats(prevn.dur)
            if ntime < 1 and not options.float:
                ntime = 1
            print maybe_int(440.0 * 2**((prevn.pitch-69)/12.0)), maybe_int(ntime),
        prevn = n
    ntime = to_beats(n.dur)
    if ntime < 1 and not options.float:
        ntime = 1
    print int(440.0 * 2**((n.pitch-69)/12.0)), int(ntime),
