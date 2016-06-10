'''
itl_chorus -- ITL Chorus Suite
mkiv -- Make Intervals

This simple script (using python-midi) reads a MIDI file and makes an interval
(.iv) file (actually XML) that contains non-overlapping notes.

TODO:
-MIDI Control events
-Percussion
'''

import xml.etree.ElementTree as ET
import midi
import sys
import os
import optparse

TRACKS = object()
PROGRAMS = object()

parser = optparse.OptionParser()
parser.add_option('-s', '--channel-split', dest='chansplit', action='store_true', help='Split MIDI channels into independent tracks (as far as -T is concerned)')
parser.add_option('-S', '--split-out', dest='chansfname', help='Store the split-format MIDI back into the specified file')
parser.add_option('-c', '--preserve-channels', dest='chanskeep', action='store_true', help='Keep the channel number when splitting channels to tracks (default is to set it to 1)')
parser.add_option('-T', '--track-split', dest='tracks', action='append_const', const=TRACKS, help='Ensure all tracks are on non-mutual streams')
parser.add_option('-t', '--track', dest='tracks', action='append', help='Reserve an exclusive set of streams for certain conditions (try --help-conds)')
parser.add_option('--help-conds', dest='help_conds', action='store_true', help='Print help on filter conditions for streams')
parser.add_option('-p', '--program-split', dest='tracks', action='append_const', const=PROGRAMS, help='Ensure all programs are on non-mutual streams (overrides -T presently)')
parser.add_option('-P', '--percussion', dest='perc', help='Which percussion standard to use to automatically filter to "perc" (GM, GM2, or none)')
parser.add_option('-f', '--fuckit', dest='fuckit', action='store_true', help='Use the Python Error Steamroller when importing MIDIs (useful for extended formats)')
parser.add_option('-n', '--target-num', dest='repeaterNumber', type='int', help='Target count of devices')
parser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Be verbose; show important parts about the MIDI scheduling process')
parser.add_option('-d', '--debug', dest='debug', action='store_true', help='Debugging output; show excessive output about the MIDI scheduling process')
parser.add_option('-D', '--deviation', dest='deviation', type='int', help='Amount (in semitones/MIDI pitch units) by which a fully deflected pitchbend modifies the base pitch (0 disables pitchbend processing)')
parser.set_defaults(tracks=[], repeaterNumber=1, perc='GM', deviation=2)
options, args = parser.parse_args()

if options.help_conds:
    print '''Filter conditions are used to route events to groups of streams.

Every filter is an expression; internally, this expression is evaluated as the body of a "lambda ev: ".
The "ev" object will be a MergeEvent with the following properties:
-ev.tidx: the originating track index (starting at 0)
-ev.abstime: the real time in seconds of this event relative to the beginning of playback
-ev.bank: the selected bank (all bits)
-ev.prog: the selected program
-ev.ev: a midi.NoteOnEvent:
    -ev.ev.pitch: the MIDI pitch
    -ev.ev.velocity: the MIDI velocity
    -ev.ev.channel: the MIDI channel

All valid Python expressions are accepted. Take care to observe proper shell escaping.

Specifying a -t <group>=<filter> will group all streams under a filter; if the <group> part is omitted, no group will be added.
For example:

    mkiv -t bass=ev.ev.pitch<35 -t treble=ev.ev.pitch>75 -T -t ev.abstime<10

will cause these groups to be made:
-A group "bass" with all notes with pitch less than 35;
-Of those not in "bass", a group in "treble" with pitch>75;
-Of what is not yet consumed, a series of groups "trkN" where N is the track index (starting at 0), which consumes the rest.
-An (unfortunately empty) unnamed group with events prior to ten real seconds.

As can be seen, order of specification is important. Equally important is the location of -T, which should be at the end.

NoteOffEvents are always matched to the stream which has their corresponding NoteOnEvent (in track, pitch, and channel), and so are
not affected or observed by filters.

If the filters specified are not a complete cover, an anonymous group will be created with no filter to contain the rest. If
it is desired to force this group to have a name, use -t <group>=True. This should be placed at the end.

-T behaves exactly as if:
    -t trk0=ev.tidx==0 -t trk1=ev.tidx==1 -t trk2=ev.tidx==2 [...]
had been specified in its place, though it is automatically sized to the number of tracks. Similarly, -P operates as if
    -t prg31=ev.prog==31 -t prg81=ev.prog==81 [...]
had been specified, again containing only the programs that were observed in the piece.

Groups for which no streams are generated are not written to the resulting file.'''
    exit()

if not args:
    parser.print_usage()
    exit()

if options.fuckit:
    import fuckit
    midi.read_midifile = fuckit(midi.read_midifile)

for fname in args:
    try:
        pat = midi.read_midifile(fname)
    except Exception:
        import traceback
        traceback.print_exc()
        print fname, ': Exception occurred, skipping...'
        continue
    if pat is None:
        print fname, ': Too fucked to continue'
        continue
    iv = ET.Element('iv')
    iv.set('version', '1')
    iv.set('src', os.path.basename(fname))
    print fname, ': MIDI format,', len(pat), 'tracks'
    if options.verbose:
        print fname, ': MIDI Parameters:', pat.resolution, 'PPQN,', pat.format, 'format'

    if options.chansplit:
        print 'Splitting channels...'
        old_pat = pat
        pat = midi.Pattern(resolution=old_pat.resolution)
        for track in old_pat:
            chan_map = {}
            last_abstick = {}
            absticks = 0
            for ev in track:
                absticks += ev.tick
                if isinstance(ev, midi.Event):
                    tick = absticks - last_abstick.get(ev.channel, 0)
                    last_abstick[ev.channel] = absticks
                    if options.chanskeep:
                        newev = ev.copy(tick = tick)
                    else:
                        newev = ev.copy(channel=1, tick = tick)
                    chan_map.setdefault(ev.channel, midi.Track()).append(newev)
                else: # MetaEvent
                    for trk in chan_map.itervalues():
                        trk.append(ev)
            items = chan_map.items()
            items.sort(key=lambda pair: pair[0])
            for chn, trk in items:
                pat.append(trk)
        print 'Split', len(old_pat), 'tracks into', len(pat), 'tracks by channel'

        if options.chansfname:
            midi.write_midifile(options.chansfname, pat)

##### Merge events from all tracks into one master list, annotated with track and absolute times #####
    print 'Merging events...'

    class SortEvent(object):
        __slots__ = ['ev', 'tidx', 'abstick']
        def __init__(self, ev, tidx, abstick):
            self.ev = ev
            self.tidx = tidx
            self.abstick = abstick

    sorted_events = []
    for tidx, track in enumerate(pat):
        absticks = 0
        for ev in track:
            absticks += ev.tick
            sorted_events.append(SortEvent(ev, tidx, absticks))

    sorted_events.sort(key=lambda x: x.abstick)
    bpm_at = [{0: 120} for i in pat]

    print 'Computing tempos...'

    for sev in sorted_events:
        if isinstance(sev.ev, midi.SetTempoEvent):
            if options.debug:
                print fname, ': SetTempo at', sev.abstick, 'to', sev.ev.bpm, ':', sev.ev
            bpm_at[sev.tidx][sev.abstick] = sev.ev.bpm

    if options.verbose:
        print fname, ': Events:', len(sorted_events)
        print fname, ': Resolved global BPM:', bpm_at
        if options.debug:
            for tidx, bpms in enumerate(bpm_at):
                print fname, ': Tempos in track', tidx
                btimes = bpms.keys()
                for i in range(len(btimes) - 1):
                    fev = filter(lambda sev: sev.tidx == tidx and sev.abstick >= btimes[i] and sev.abstick < btimes[i+1], sorted_events)
                    print fname, ': BPM partition', i, 'contains', len(fev), 'events'

    class MergeEvent(object):
        __slots__ = ['ev', 'tidx', 'abstime', 'bank', 'prog']
        def __init__(self, ev, tidx, abstime, bank, prog):
            self.ev = ev
            self.tidx = tidx
            self.abstime = abstime
            self.bank = bank
            self.prog = prog
        def copy(self, **kwargs):
            args = {'ev': self.ev, 'tidx': self.tidx, 'abstime': self.abstime, 'bank': self.bank, 'prog': self.prog}
            args.update(kwargs)
            return MergeEvent(**args)
        def __repr__(self):
            return '<ME %r in %d on (%d:%d) @%f>'%(self.ev, self.tidx, self.bank, self.prog, self.abstime)

    events = []
    cur_bank = [[0 for i in range(16)] for j in range(len(pat))]
    cur_prog = [[0 for i in range(16)] for j in range(len(pat))]
    chg_bank = [[0 for i in range(16)] for j in range(len(pat))]
    chg_prog = [[0 for i in range(16)] for j in range(len(pat))]
    ev_cnts = [[0 for i in range(16)] for j in range(len(pat))]
    tnames = [''] * len(pat)
    progs = set([0])

    for tidx, track in enumerate(pat):
        abstime = 0
        absticks = 0
        for ev in track:
            bpm = filter(lambda pair: pair[0] <= absticks, sorted(bpm_at[tidx].items(), key=lambda pair: pair[0]))[-1][1]
            if options.debug:
                print ev, ': bpm=', bpm
            absticks += ev.tick
            if isinstance(ev, midi.ProgramChangeEvent):
                cur_prog[tidx][ev.channel] = ev.value
                progs.add(ev.value)
                chg_prog[tidx][ev.channel] += 1
            elif isinstance(ev, midi.ControlChangeEvent):
                if ev.control == 0:
                    cur_bank[tidx][ev.channel] = (0x3F80 & cur_bank[tidx][ev.channel]) | ev.value
                    chg_bank[tidx][ev.channel] += 1
                elif ev.control == 32:
                    cur_bank[tidx][ev.channel] = (0x3F & cur_bank[tidx][ev.channel]) | (ev.value << 7)
                    chg_bank[tidx][ev.channel] += 1
            elif isinstance(ev, midi.TrackNameEvent):
                tnames[tidx] = ev.text
            elif isinstance(ev, midi.Event):
                if isinstance(ev, midi.NoteOnEvent) and ev.velocity == 0:
                    ev.__class__ = midi.NoteOffEvent #XXX Oww
                abstime += (60.0 * ev.tick) / (bpm * pat.resolution)
                events.append(MergeEvent(ev, tidx, abstime, cur_bank[tidx][ev.channel], cur_prog[tidx][ev.channel]))
                ev_cnts[tidx][ev.channel] += 1

    if options.verbose:
        print 'Track name, event count, final banks, bank changes, final programs, program changes:'
        for tidx, tname in enumerate(tnames):
            print tidx, ':', tname, ',', ','.join(map(str, ev_cnts[tidx])), ',', ','.join(map(str, cur_bank[tidx])), ',', ','.join(map(str, chg_bank[tidx])), ',', ','.join(map(str, cur_prog[tidx])), ',', ','.join(map(str, chg_prog[tidx]))
        print 'All programs observed:', progs

    print 'Sorting events...'

    events.sort(key = lambda ev: ev.abstime)

##### Use merged events to construct a set of streams with non-overlapping durations #####
    print 'Generating streams...'

    class DurationEvent(MergeEvent):
        __slots__ = ['duration', 'pitch']
        def __init__(self, me, pitch, dur):
            MergeEvent.__init__(self, me.ev, me.tidx, me.abstime, me.bank, me.prog)
            self.pitch = pitch
            self.duration = dur

    class NoteStream(object):
        __slots__ = ['history', 'active', 'realpitch']
        def __init__(self):
            self.history = []
            self.active = None
            self.realpitch = None
        def IsActive(self):
            return self.active is not None
        def Activate(self, mev, realpitch = None):
            if realpitch is None:
                realpitch = mev.ev.pitch
            self.active = mev
            self.realpitch = realpitch
        def Deactivate(self, mev):
            self.history.append(DurationEvent(self.active, self.realpitch, mev.abstime - self.active.abstime))
            self.active = None
            self.realpitch = None
        def WouldDeactivate(self, mev):
            if not self.IsActive():
                return False
            if isinstance(mev.ev, midi.NoteOffEvent):
                return mev.ev.pitch == self.active.ev.pitch and mev.tidx == self.active.tidx and mev.ev.channel == self.active.ev.channel
            if isinstance(mev.ev, midi.PitchWheelEvent):
                return mev.tidx == self.active.tidx and mev.ev.channel == self.active.ev.channel
            raise TypeError('Tried to deactivate with bad type %r'%(type(mev.ev),))

    class NSGroup(object):
        __slots__ = ['streams', 'filter', 'name']
        def __init__(self, filter=None, name=None):
            self.streams = []
            self.filter = (lambda mev: True) if filter is None else filter
            self.name = name
        def Accept(self, mev):
            if not self.filter(mev):
                return False
            for stream in self.streams:
                if not stream.IsActive():
                    stream.Activate(mev)
                    break
            else:
                stream = NoteStream()
                self.streams.append(stream)
                stream.Activate(mev)
            return True

    notegroups = []
    auxstream = []

    if options.perc and options.perc != 'none':
        if options.perc == 'GM':
            notegroups.append(NSGroup(filter = lambda mev: mev.ev.channel == 9, name='perc'))
        elif options.perc == 'GM2':
            notegroups.append(NSGroup(filter = lambda mev: mev.bank == 15360, name='perc'))
        else:
            print 'Unrecognized --percussion option %r; should be GM, GM2, or none'%(options.perc,)

    for spec in options.tracks:
        if spec is TRACKS:
            for tidx in xrange(len(pat)):
                notegroups.append(NSGroup(filter = lambda mev, tidx=tidx: mev.tidx == tidx, name = 'trk%d'%(tidx,)))
        elif spec is PROGRAMS:
            for prog in progs:
                notegroups.append(NSGroup(filter = lambda mev, prog=prog: mev.prog == prog, name = 'prg%d'%(prog,)))
        else:
            if '=' in spec:
                name, _, spec = spec.partition('=')
            else:
                name = None
            notegroups.append(NSGroup(filter = eval("lambda ev: "+spec), name = name))

    if options.verbose:
        print 'Initial group mappings:'
        for group in notegroups:
            print ('<anonymous>' if group.name is None else group.name)

    for mev in events:
        if isinstance(mev.ev, midi.NoteOnEvent):
            for group in notegroups:
                if group.Accept(mev):
                    break
            else:
                group = NSGroup()
                group.Accept(mev)
                notegroups.append(group)
        elif isinstance(mev.ev, midi.NoteOffEvent):
            for group in notegroups:
                found = False
                for stream in group.streams:
                    if stream.WouldDeactivate(mev):
                        stream.Deactivate(mev)
                        found = True
                        break
                if found:
                    break
            else:
                print 'WARNING: Did not match %r with any stream deactivation.'%(mev,)
                if options.verbose:
                    print '  Current state:'
                    for group in notegroups:
                        print '    Group %r:'%(group.name,)
                        for stream in group.streams:
                            print '      Stream: %r'%(stream.active,)
        elif options.deviation > 0 and isinstance(mev.ev, midi.PitchWheelEvent):
            for group in notegroups:
                found = False
                for stream in group.streams:
                    if stream.WouldDeactivate(mev):
                        base = stream.active.copy(abstime=mev.abstime)
                        stream.Deactivate(mev)
                        stream.Activate(base, base.ev.pitch + options.deviation * (mev.ev.pitch / 2000.0))
                        found = True
                        break
                if found:
                    break
            else:
                print 'WARNING: Did not find any matching active streams for %r'%(mev,)
                if options.verbose:
                    print '  Current state:'
                    for group in notegroups:
                        print '    Group %r:'%(group.name,)
                        for stream in group.streams:
                            print '      Stream: %r'%(stream.active,)
        else:
            auxstream.append(mev)

    lastabstime = events[-1].abstime

    for group in notegroups:
        for ns in group.streams:
            if ns.IsActive():
                print 'WARNING: Active notes at end of playback.'
                ns.Deactivate(MergeEvent(ns.active, ns.active.tidx, lastabstime, 0, 0))

    if options.verbose:
        print 'Final group mappings:'
        for group in notegroups:
            print ('<anonymous>' if group.name is None else group.name), '<=', '(', len(group.streams), 'streams)'

    print 'Generated %d streams in %d groups'%(sum(map(lambda x: len(x.streams), notegroups)), len(notegroups))
    print 'Playtime:', lastabstime, 'seconds'

##### Write to XML and exit #####

    ivmeta = ET.SubElement(iv, 'meta')
    abstime = 0
    prevticks = 0
    prev_bpm = 120
    for tidx, bpms in enumerate(bpm_at):
        ivbpms = ET.SubElement(ivmeta, 'bpms', track=str(tidx))
        for absticks, bpm in sorted(bpms.items(), key = lambda pair: pair[0]):
            abstime += ((absticks - prevticks) * 60.0) / (prev_bpm * pat.resolution)
            prevticks = absticks
            ivbpm = ET.SubElement(ivbpms, 'bpm')
            ivbpm.set('bpm', str(bpm))
            ivbpm.set('ticks', str(absticks))
            ivbpm.set('time', str(abstime))

    ivstreams = ET.SubElement(iv, 'streams')

    x = 0 
    while(x<options.repeaterNumber):
    	for group in notegroups:
        	for ns in group.streams:
            		ivns = ET.SubElement(ivstreams, 'stream')
            		ivns.set('type', 'ns')
           		if group.name is not None:
                		ivns.set('group', group.name)
            		for note in ns.history:
                		ivnote = ET.SubElement(ivns, 'note')
                		ivnote.set('pitch', str(note.pitch))
              			ivnote.set('vel', str(note.ev.velocity))
        	       		ivnote.set('time', str(note.abstime))
 	               		ivnote.set('dur', str(note.duration))
			x+=1
			if(x>=options.repeaterNumber and options.repeaterNumber!=1):
				break
		if(x>=options.repeaterNumber and options.repeaterNumber!=1):
			break
	if(x>=options.repeaterNumber and options.repeaterNumber!=1):
		break

    ivaux = ET.SubElement(ivstreams, 'stream')
    ivaux.set('type', 'aux')

    fw = midi.FileWriter()
    fw.RunningStatus = None # XXX Hack

    for mev in auxstream:
        ivev = ET.SubElement(ivaux, 'ev')
        ivev.set('time', str(mev.abstime))
        ivev.set('data', repr(fw.encode_midi_event(mev.ev)))

    print 'Done.'
    open(os.path.splitext(os.path.basename(fname))[0]+'.iv', 'w').write(ET.tostring(iv))
