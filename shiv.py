# IV file viewer

import xml.etree.ElementTree as ET
import optparse
import sys
import math

parser = optparse.OptionParser()
parser.add_option('-n', '--number', dest='number', action='store_true', help='Show number of tracks')
parser.add_option('-g', '--groups', dest='groups', action='store_true', help='Show group names')
parser.add_option('-N', '--notes', dest='notes', action='store_true', help='Show number of notes')
parser.add_option('-M', '--notes-stream', dest='notes_stream', action='store_true', help='Show notes per stream')
parser.add_option('-m', '--meta', dest='meta', action='store_true', help='Show meta track information')
parser.add_option('--histogram', dest='histogram', action='store_true', help='Show a histogram distribution of pitches')
parser.add_option('--histogram-tracks', dest='histogram_tracks', action='store_true', help='Show a histogram distribution of pitches per track')
parser.add_option('--vel-hist', dest='vel_hist', action='store_true', help='Show a histogram distribution of velocities')
parser.add_option('--vel-hist-tracks', dest='vel_hist_tracks', action='store_true', help='Show a histogram distributions of velocities per track')
parser.add_option('-d', '--duration', dest='duration', action='store_true', help='Show the duration of the piece')
parser.add_option('-D', '--duty-cycle', dest='duty_cycle', action='store_true', help='Show the duration of the notes within tracks, and as a percentage of the piece duration')
parser.add_option('-H', '--height', dest='height', type='int', help='Height of histograms')
parser.add_option('-C', '--no-color', dest='no_color', action='store_true', help='Don\'t use ANSI color escapes')
parser.add_option('-x', '--aux', dest='aux', action='store_true', help='Show information about the auxiliary streams')

parser.add_option('-a', '--almost-all', dest='almost_all', action='store_true', help='Show useful information')
parser.add_option('-A', '--all', dest='all', action='store_true', help='Show everything')

parser.set_defaults(height=20)

options, args = parser.parse_args()

if options.almost_all or options.all:
    options.number = True
    options.groups = True
    options.notes = True
    options.notes_stream = True
    options.histogram = True
    options.vel_hist = True
    options.duration = True
    options.duty_cycle = True
    if options.all:
        options.aux = True
        options.meta = True
        options.histogram_tracks= True
        options.vel_hist_tracks = True

if options.no_color:
    class COL:
        NONE=''
        RED=''
        GREEN=''
        BLUE=''
        YELLOW=''
        MAGENTA=''
        CYAN=''
else:
    class COL:
        NONE='\x1b[0m'
        RED='\x1b[31m'
        GREEN='\x1b[32m'
        BLUE='\x1b[34m'
        YELLOW='\x1b[33m'
        MAGENTA='\x1b[35m'
        CYAN='\x1b[36m'

def show_hist(values, height=None):
    if not values:
        print '{empty histogram}'
    if height is None:
        height = options.height
    xs, ys = values.keys(), values.values()
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    xv = range(int(math.floor(minx)), int(math.ceil(maxx + 1)))
    incs = max((maxy - miny) / height, 1)
    print COL.CYAN + '\t --' + '-' * len(xv) + COL.NONE
    for ub in range(maxy + incs, miny, -incs):
        print '{}{}\t | {}{}{}'.format(COL.CYAN, ub, COL.YELLOW, ''.join(['#' if values.get(x) > (ub - incs) else ' ' for x in xv]), COL.NONE)
    print COL.CYAN + '\t |-' + '-' * len(xv) + COL.NONE
    xvs = map(str, xv)
    for i in range(max(map(len, xvs))):
        print COL.CYAN + '\t   ' + ''.join([s[i] if len(s) > i else ' ' for s in xvs]) + COL.NONE
    print
    xcs = map(str, [values.get(x, 0) for x in xv])
    for i in range(max(map(len, xcs))):
        print COL.YELLOW + '\t   ' + ''.join([s[i] if len(s) > i else ' ' for s in xcs]) + COL.NONE
    print

for fname in args:
    try:
        iv = ET.parse(fname).getroot()
    except IOError:
        import traceback
        traceback.print_exc()
        print 'Bad file :', fname, ', skipping...'
        continue
    print
    print 'File :', fname
    print '\t<computing...>'

    if options.meta:
        print 'Metatrack:',
        meta = iv.find('./meta')
        if len(meta):
            print 'exists'
            print '\tBPM track:',
            bpms = meta.find('./bpms')
            if len(bpms):
                print 'exists'
                for elem in bpms.iterfind('./bpm'):
                    print '\t\tAt ticks {}, time {}: {} bpm'.format(elem.get('ticks'), elem.get('time'), elem.get('bpm'))

    if not (options.number or options.groups or options.notes or options.histogram or options.histogram_tracks or options.vel_hist or options.vel_hist_tracks or options.duration or options.duty_cycle or options.aux):
        continue

    streams = iv.findall('./streams/stream')
    notestreams = [s for s in streams if s.get('type') == 'ns']
    auxstreams = [s for s in streams if s.get('type') == 'aux']
    if options.number:
        print 'Stream count:'
        print '\tNotestreams:', len(notestreams)
        print '\tTotal:', len(streams)

    if not (options.groups or options.notes or options.histogram or options.histogram_tracks or options.vel_hist or options.vel_hist_tracks or options.duration or options.duty_cycle or options.aux):
        continue

    if options.groups:
        groups = {}
        for s in notestreams:
            group = s.get('group', '<anonymous>')
            groups[group] = groups.get(group, 0) + 1
        print 'Groups:'
        for name, cnt in groups.iteritems():
            print '\t{} ({} streams)'.format(name, cnt)

    if options.aux:
        import midi
        fr = midi.FileReader()
        fr.RunningStatus = None  # XXX Hack
        print 'Aux stream data:'
        for aidx, astream in enumerate(auxstreams):
            evs = astream.findall('ev')
            failed = 0
            print '\tFrom stream {}, {} events:'.format(aidx, len(evs))
            for ev in evs:
                try:
                    data = eval(ev.get('data'))
                    mev = fr.parse_midi_event(iter(data))
                except AssertionError:
                    failed += 1
                else:
                    print '\t\tAt time {}: {}'.format(ev.get('time'), mev)
            print '\t\t(...and {} others which failed to parse)'.format(failed)

    if not (options.notes or options.notes_stream or options.histogram or options.histogram_tracks or options.vel_hist or options.vel_hist_tracks or options.duration or options.duty_cycle):
        continue

    if options.notes:
        note_cnt = 0
    if options.notes_stream:
        notes_stream = [0] * len(notestreams)
    if options.histogram:
        pitches = {}
    if options.histogram_tracks:
        pitch_tracks = [{} for i in notestreams]
    if options.vel_hist:
        velocities = {}
    if options.vel_hist_tracks:
        velocities_tracks = [{} for i in notestreams]
    if options.duration or options.duty_cycle:
        max_dur = 0
    if options.duty_cycle:
        cum_dur = [0.0] * len(notestreams)

    for sidx, stream in enumerate(notestreams):
        notes = stream.findall('note')
        for note in notes:
            pitch = float(note.get('pitch'))
            vel = int(note.get('vel'))
            time = float(note.get('time'))
            dur = float(note.get('dur'))
            if options.notes:
                note_cnt += 1
            if options.notes_stream:
                notes_stream[sidx] += 1
            if options.histogram:
                pitches[pitch] = pitches.get(pitch, 0) + 1
            if options.histogram_tracks:
                pitch_tracks[sidx][pitch] = pitch_tracks[sidx].get(pitch, 0) + 1
            if options.vel_hist:
                velocities[vel] = velocities.get(vel, 0) + 1
            if options.vel_hist_tracks:
                velocities_tracks[sidx][vel] = velocities_tracks[sidx].get(vel, 0) + 1
            if (options.duration or options.duty_cycle) and time + dur > max_dur:
                max_dur = time + dur
            if options.duty_cycle:
                cum_dur[sidx] += dur

    if options.histogram_tracks:
        for sidx, hist in enumerate(pitch_tracks):
            print 'Stream {} (group {}) pitch histogram:'.format(sidx, notestreams[sidx].get('group', '<anonymous>'))
            show_hist(hist)
    if options.vel_hist_tracks:
        for sidx, hist in enumerate(velocities_tracks):
            print 'Stream {} (group {}) velocity histogram:'.format(sidx, notestreams[sidx].get('group', '<anonymous>'))
            show_hist(hist)
    if options.notes_stream:
        for sidx, value in enumerate(notes_stream):
            print 'Stream {} (group {}) note count: {}'.format(sidx, notestreams[sidx].get('group', '<anonymous>'), value)
    if options.duty_cycle:
        for sidx, value in enumerate(cum_dur):
            print 'Stream {} (group {}) duty cycle: {}'.format(sidx, notestreams[sidx].get('group', '<anonymous>'), value / max_dur)
    if options.notes:
        print 'Total notes: {}'.format(note_cnt)
    if options.histogram:
        print 'Pitch histogram:'
        show_hist(pitches)
    if options.vel_hist:
        print 'Velocity histogram:'
        show_hist(velocities)
    if options.duration:
        print 'Playing duration: {}'.format(max_dur)
