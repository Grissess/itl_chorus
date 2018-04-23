from xml.etree import ElementTree as ET
import optparse
import os

parser = optparse.OptionParser()
parser.add_option('-f', '--frequency', dest='frequency', type='float', help='How often to switch between active streams')
parser.set_defaults(frequency=0.016)
options, args = parser.parse_args()

class Note(object):
    def __init__(self, time, dur, pitch, ampl):
        self.time = time
        self.dur = dur
        self.pitch = pitch
        self.ampl = ampl

for fname in args:
    try:
        iv = ET.parse(fname).getroot()
    except IOError:
        import traceback
        traceback.print_exc()
        print fname, ': Bad file'
        continue

    print '----', fname, '----'

    notestreams = iv.findall("./streams/stream[@type='ns']")
    print len(notestreams), 'notestreams'

    print 'Loading all events...'

    evs = []

    dur = 0.0

    for ns in notestreams:
        for note in ns.findall('note'):
            n = Note(
                float(note.get('time')),
                float(note.get('dur')),
                float(note.get('pitch')),
                float(note.get('ampl', float(note.get('vel', 127.0)) / 127.0)),
            )
            evs.append(n)
            if n.time + n.dur > dur:
                dur = n.time + n.dur

    print len(evs), 'events'
    print dur, 'duration'

    print 'Scheduling events...'

    sched = {}

    t = 0.0
    i = 0
    while t <= dur:
        nextt = t + options.frequency
        #print '-t', t, 'nextt', nextt

        evs_now = [n for n in evs if n.time <= t and t < n.time + n.dur]
        if evs_now:
            holding = False
            count = 0
            while count < len(evs_now):
                selidx = (count + i) % len(evs_now)
                sel = evs_now[selidx]
                sched[t] = (sel.pitch, sel.ampl)
                if sel.time + sel.dur >= nextt:
                    holding = True
                    break
                t = sel.time + sel.dur
                count += 1
            if not holding:
                sched[t] = (0, 0)
        else:
            sched[t] = (0, 0)

        t = nextt
        i += 1

    print len(sched), 'events scheduled'

    print 'Writing out schedule...'

    newiv = ET.Element('iv')
    newiv.append(iv.find('meta'))
    newivstreams = ET.SubElement(newiv, 'streams')
    newivstream = ET.SubElement(newivstreams, 'stream', type='ns')

    prevt = None
    prevev = None
    for t, ev in sorted(sched.items(), key=lambda pair: pair[0]):
        if prevt is not None:
            if prevev[0] != 0:
                ET.SubElement(newivstream, 'note',
                        pitch = str(prevev[0]),
                        ampl = str(prevev[1]),
                        time = str(prevt),
                        dur = str(t - prevt),
                )
        prevev = ev
        prevt = t

    t = dur
    if prevev[0] != 0:
        ET.SubElement(newivstream, 'note',
                pitch = str(prevev[0]),
                ampl = str(prevev[1]),
                time = str(prevt),
                dur = str(t - prevt),
        )

    print 'Done.'
    txt = ET.tostring(newiv, 'UTF-8')
    open(os.path.splitext(os.path.basename(fname))[0]+'.downsampled.iv', 'wb').write(txt)
