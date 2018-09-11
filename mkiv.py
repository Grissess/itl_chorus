'''
itl_chorus -- ITL Chorus Suite
mkiv -- Make Intervals

This simple script (using python-midi) reads a MIDI file and makes an interval
(.iv) file (actually XML) that contains non-overlapping notes.
'''

import xml.etree.ElementTree as ET
import midi
import sys
import os
import optparse
import math

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
parser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Be verbose; show important parts about the MIDI scheduling process')
parser.add_option('-d', '--debug', dest='debug', action='store_true', help='Debugging output; show excessive output about the MIDI scheduling process (please use less or write to a file)')
parser.add_option('-D', '--deviation', dest='deviation', type='int', help='Amount (in semitones/MIDI pitch units) by which a fully deflected pitchbend modifies the base pitch (0 disables pitchbend processing)')
parser.add_option('-M', '--modwheel-freq-dev', dest='modfdev', type='float', help='Amount (in semitones/MIDI pitch unites) by which a fully-activated modwheel modifies the base pitch')
parser.add_option('--modwheel-freq-freq', dest='modffreq', type='float', help='Frequency of modulation periods (sinusoids) of the modwheel acting on the base pitch')
parser.add_option('--modwheel-amp-dev', dest='modadev', type='float', help='Deviation [0, 1] by which a fully-activated modwheel affects the amplitude as a factor of that amplitude')
parser.add_option('--modwheel-amp-freq', dest='modafreq', type='float', help='Frequency of modulation periods (sinusoids) of the modwheel acting on amplitude')
parser.add_option('--modwheel-res', dest='modres', type='float', help='(Fractional) seconds by which to resolve modwheel events (0 to disable)')
parser.add_option('--modwheel-continuous', dest='modcont', action='store_true', help='Keep phase continuous in global time (don\'t reset to 0 for each note)')
parser.add_option('--string-res', dest='stringres', type='float', help='(Fractional) seconds by which to resolve string models (0 to disable)')
parser.add_option('--string-max', dest='stringmax', type='int', help='Maximum number of events to generate per single input event')
parser.add_option('--string-rate-on', dest='stringonrate', type='float', help='Rate (amplitude / sec) by which to exponentially decay in the string model while a note is active')
parser.add_option('--string-rate-off', dest='stringoffrate', type='float', help='Rate (amplitude / sec) by which to exponentially decay in the string model after a note ends')
parser.add_option('--string-threshold', dest='stringthres', type='float', help='Amplitude (as fraction of original) at which point the string model event is terminated')
parser.add_option('--tempo', dest='tempo', help='Adjust interpretation of tempo (try "f1"/"global", "f2"/"track")')
parser.add_option('--epsilon', dest='epsilon', type='float', help='Don\'t consider overlaps smaller than this number of seconds (which regularly happen due to precision loss)')
parser.add_option('--slack', dest='slack', type='float', help='Inflate the duration of events by this much when scheduling them--this is for clients which need time to release their streams')
parser.add_option('--vol-pow', dest='vol_pow', type='float', help='Exponent to raise volume changes (adjusts energy per delta volume)')
parser.add_option('-0', '--keep-empty', dest='keepempty', action='store_true', help='Keep (do not cull) events with 0 duration in the output file')
parser.add_option('--no-text', dest='no_text', action='store_true', help='Disable text streams (useful for unusual text encodings)')
parser.add_option('--no-wav', dest='no_wav', action='store_true', help='Disable processing of WAVE files')
parser.add_option('--wav-winf', dest='wav_winf', help='Window function (on numpy) to use for FFT calculation')
parser.add_option('--wav-frames', dest='wav_frames', type='int', help='Number of frames to read per FFT calculation')
parser.add_option('--wav-window', dest='wav_window', type='int', help='Size of the FFT window')
parser.add_option('--wav-streams', dest='wav_streams', type='int', help='Number of output streams to generate for the interval file')
parser.add_option('--wav-log-width', dest='wav_log_width', type='float', help='Width of the correcting exponent--positive prefers high frequencies, negative prefers lower')
parser.add_option('--wav-log-base', dest='wav_log_base', type='float', help='Base of the logarithm used to scale low frequencies')
parser.set_defaults(tracks=[], perc='GM', deviation=2, tempo='global', modres=0.005, modfdev=2.0, modffreq=8.0, modadev=0.5, modafreq=8.0, stringres=0, stringmax=1024, stringrateon=0.7, stringrateoff=0.4, stringthres=0.02, epsilon=1e-12, slack=0.0, vol_pow=2, wav_winf='ones', wav_frames=512, wav_window=2048, wav_streams=16, wav_log_width=0.0, wav_log_base=2.0)
options, args = parser.parse_args()
if options.tempo == 'f1':
    options.tempo == 'global'
elif options.tempo == 'f2':
    options.tempo == 'track'

if options.help_conds:
    print '''Filter conditions are used to route events to groups of streams.

Every filter is an expression; internally, this expression is evaluated as the body of a "lambda ev: ".
The "ev" object will be a MergeEvent with the following properties:
-ev.tidx: the originating track index (starting at 0)
-ev.abstime: the real time in seconds of this event relative to the beginning of playback
-ev.bank: the selected bank (all bits)
-ev.prog: the selected program
-ev.mw: the modwheel value
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
    if fname.endswith('.wav') and not options.no_wav:
        import wave, struct
        import numpy as np
        wf = wave.open(fname, 'rb')
        chan, width, rate, frames, cmptype, cmpname = wf.getparams()
        print fname, ': WAV file, ', chan, 'channels,', width, 'sample width,', rate, 'sample rate,', frames, 'total frames,', cmpname
        sty = [None, np.int8, np.int16, None, np.int32][width]
        window = np.zeros((options.wav_window,))
        cnt = 0
        freqs = []
        amps = []
        winf = getattr(np, options.wav_winf)(options.wav_window)
        freqwin = np.fft.rfftfreq(options.wav_window, 1.0 / rate)[1:]
        logwin = np.logspace(-options.wav_log_width, options.wav_log_width, len(freqwin), True, options.wav_log_base)
        while True:
            sampsraw = wf.readframes(options.wav_frames)
            cnt += len(sampsraw) / (width * chan)
            if len(sampsraw) < options.wav_frames * chan * width:
                break
            window = np.concatenate((window, np.frombuffer(sampsraw, dtype=sty)[::chan] / float(1 << (width * 8 - 1))))[-options.wav_window:]
            spect = logwin * (np.abs(np.fft.rfft(winf * window)) / options.wav_window)[1:]
            amspect = np.argsort(spect)[:-(options.wav_streams + 1):-1]
            freqs.append(freqwin[amspect])
            amps.append(spect[amspect] * (options.wav_window / float(options.wav_streams)))
        print 'Processed', cnt, 'frames'
        period = options.wav_frames / float(rate)
        print 'Period:', period, 'sec'
        iv = ET.Element('iv', version='1', src=os.path.basename(fname), wav='1')
        ivstreams = ET.SubElement(iv, 'streams')
        streams = [ET.SubElement(ivstreams, 'stream', type='ns') for i in range(options.wav_streams)]
        t = 0
        for fs, ams in zip(freqs, amps):
            if options.debug:
                print 'Sample at t={}: {}'.format(t, list(zip(fs, ams)))
            for stm, frq, amp in zip(streams, fs, ams):
                ivnote = ET.SubElement(stm, 'note', pitch=str(12*math.log(frq/440.0, 2)+69), amp=str(amp), vel=str(int(amp * 127.0)), time=str(t), dur=str(period))
            t += period
        print 'Writing...'
        open(os.path.splitext(os.path.basename(fname))[0] + '.iv', 'wb').write(ET.tostring(iv, 'UTF-8'))
        print 'Done.'
        continue
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
    iv.set('version', '1.1')
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
    if options.tempo == 'global':
        bpm_at = [{0: 120}]
    else:
        bpm_at = [{0: 120} for i in pat]

    print 'Computing tempos...'

    for sev in sorted_events:
        if isinstance(sev.ev, midi.SetTempoEvent):
            if options.debug:
                print fname, ': SetTempo at', sev.abstick, 'to', sev.ev.bpm, ':', sev.ev
            bpm_at[sev.tidx if options.tempo == 'track' else 0][sev.abstick] = sev.ev.bpm

    if options.verbose:
        print fname, ': Events:', len(sorted_events)
        print fname, ': Resolved global BPM:', bpm_at
        if options.debug:
            if options.tempo == 'track':
                for tidx, bpms in enumerate(bpm_at):
                    print fname, ': Tempos in track', tidx
                    btimes = bpms.keys()
                    for i in range(len(btimes) - 1):
                        fev = filter(lambda sev: sev.tidx == tidx and sev.abstick >= btimes[i] and sev.abstick < btimes[i+1], sorted_events)
                        print fname, ': BPM partition', i, 'contains', len(fev), 'events'
            else:
                btimes = bpm_at[0].keys()
                for i in range(len(btimes) - 1):
                    fev = filter(lambda sev: sev.abstick >= btimes[i] and sev.abstick < btimes[i+1], sorted_events)
                    print fname, ': BPM partition', i, 'contains', len(fev), 'events'

    def at2rt(abstick, bpms):
        bpm_segs = bpms.items()
        bpm_segs.sort(key=lambda pair: pair[0])
        bpm_segs = filter(lambda pair: pair[0] <= abstick, bpm_segs)
        rt = 0
        atick = 0
        if not bpm_segs:
            rt = 0
        else:
            ctick, bpm = bpm_segs[0]
            rt = (60.0 * ctick) / (bpm * pat.resolution)
        for idx in range(1, len(bpm_segs)):
            dt = bpm_segs[idx][0] - bpm_segs[idx-1][0]
            bpm = bpm_segs[idx-1][1]
            rt += (60.0 * dt) / (bpm * pat.resolution)
        if not bpm_segs:
            bpm = 120
            ctick = 0
        else:
            ctick, bpm = bpm_segs[-1]
        if options.debug:
            print 'seg through', bpm_segs, 'final seg', (abstick - ctick, bpm)
        rt += (60.0 * (abstick - ctick)) / (bpm * pat.resolution)
        return rt

    class MergeEvent(object):
        __slots__ = ['ev', 'tidx', 'abstime', 'bank', 'prog', 'mw', 'par']
        def __init__(self, ev, tidx, abstime, bank=0, prog=0, mw=0, par=None):
            self.ev = ev
            self.tidx = tidx
            self.abstime = abstime
            self.bank = bank
            self.prog = prog
            self.mw = mw
            self.par = par
        def copy(self, **kwargs):
            args = {'ev': self.ev, 'tidx': self.tidx, 'abstime': self.abstime, 'bank': self.bank, 'prog': self.prog, 'mw': self.mw, 'par': self.par}
            args.update(kwargs)
            return MergeEvent(**args)
        def __repr__(self):
            return '<ME %r in %d on (%d:%d) MW:%d @%f par %r>'%(self.ev, self.tidx, self.bank, self.prog, self.mw, self.abstime, self.par)

    vol_at = [[{0: 0x3FFF} for i in range(16)] for j in range(len(pat))]

    events = []
    cur_mw = [[0 for i in range(16)] for j in range(len(pat))]
    cur_bank = [[0 for i in range(16)] for j in range(len(pat))]
    cur_prog = [[0 for i in range(16)] for j in range(len(pat))]
    chg_mw = [[0 for i in range(16)] for j in range(len(pat))]
    chg_bank = [[0 for i in range(16)] for j in range(len(pat))]
    chg_prog = [[0 for i in range(16)] for j in range(len(pat))]
    chg_vol = [[0 for i in range(16)] for j in range(len(pat))]
    ev_cnts = [[0 for i in range(16)] for j in range(len(pat))]
    tnames = [''] * len(pat)
    progs = set([0])

    for tidx, track in enumerate(pat):
        abstime = 0
        absticks = 0
        lastbpm = 120
        for ev in track:
            absticks += ev.tick
            abstime = at2rt(absticks, bpm_at[tidx if options.tempo == 'track' else 0])
            if options.debug:
                print 'tick', absticks, 'realtime', abstime
            if isinstance(ev, midi.TrackNameEvent):
                tnames[tidx] = ev.text
            if isinstance(ev, midi.ProgramChangeEvent):
                cur_prog[tidx][ev.channel] = ev.value
                progs.add(ev.value)
                chg_prog[tidx][ev.channel] += 1
            elif isinstance(ev, midi.ControlChangeEvent):
                if ev.control == 0:  # Bank -- MSB
                    cur_bank[tidx][ev.channel] = (0x3F & cur_bank[tidx][ev.channel]) | (ev.value << 7)
                    chg_bank[tidx][ev.channel] += 1
                elif ev.control == 32:  # Bank -- LSB
                    cur_bank[tidx][ev.channel] = (0x3F80 & cur_bank[tidx][ev.channel]) | ev.value
                    chg_bank[tidx][ev.channel] += 1
                elif ev.control == 1:  # ModWheel -- MSB
                    cur_mw[tidx][ev.channel] = (0x3F & cur_mw[tidx][ev.channel]) | (ev.value << 7)
                    chg_mw[tidx][ev.channel] += 1
                elif ev.control == 33:  # ModWheel -- LSB
                    cur_mw[tidx][ev.channel] = (0x3F80 & cur_mw[tidx][ev.channel]) | ev.value
                    chg_mw[tidx][ev.channel] += 1
                elif ev.control == 7:  # Volume -- MSB
                    lvtime, lvol = sorted(vol_at[tidx][ev.channel].items(), key = lambda pair: pair[0])[-1]
                    vol_at[tidx][ev.channel][abstime] = (0x3F & lvol) | (ev.value << 7)
                    chg_vol[tidx][ev.channel] += 1
                elif ev.control == 39:  # Volume -- LSB
                    lvtime, lvol = sorted(vol_at[tidx][ev.channel].items(), key = lambda pair: pair[0])[-1]
                    vol_at[tidx][ev.channel][abstime] = (0x3F80 & lvol) | ev.value
                    chg_vol[tidx][ev.channel] += 1
                events.append(MergeEvent(ev, tidx, abstime, cur_bank[tidx][ev.channel], cur_prog[tidx][ev.channel], cur_mw[tidx][ev.channel], events[-1]))
                ev_cnts[tidx][ev.channel] += 1
            elif isinstance(ev, midi.MetaEventWithText):
                events.append(MergeEvent(ev, tidx, abstime))
            elif isinstance(ev, midi.Event):
                if isinstance(ev, midi.NoteOnEvent) and ev.velocity == 0:
                    ev.__class__ = midi.NoteOffEvent #XXX Oww
                events.append(MergeEvent(ev, tidx, abstime, cur_bank[tidx][ev.channel], cur_prog[tidx][ev.channel], cur_mw[tidx][ev.channel]))
                ev_cnts[tidx][ev.channel] += 1

    print 'Track name, event count, final banks, bank changes, final programs, program changes, final modwheel, modwheel changes, volume changes:'
    for tidx, tname in enumerate(tnames):
        print tidx, ':', tname, ',', ','.join(map(str, ev_cnts[tidx])), ',', ','.join(map(str, cur_bank[tidx])), ',', ','.join(map(str, chg_bank[tidx])), ',', ','.join(map(str, cur_prog[tidx])), ',', ','.join(map(str, chg_prog[tidx])), ',', ','.join(map(str, cur_mw[tidx])), ',', ','.join(map(str, chg_mw[tidx])), ',', ','.join(map(str, chg_vol[tidx]))
    print 'All programs observed:', progs

    print 'Sorting events...'

    events.sort(key = lambda ev: ev.abstime)

##### Use merged events to construct a set of streams with non-overlapping durations #####
    print 'Generating streams...'

    class DurationEvent(MergeEvent):
        __slots__ = ['duration', 'real_duration', 'pitch', 'modwheel', 'ampl']
        def __init__(self, me, pitch, ampl, dur, modwheel=0, par=None):
            MergeEvent.__init__(self, me.ev, me.tidx, me.abstime, me.bank, me.prog, me.mw, par)
            self.pitch = pitch
            self.ampl = ampl
            self.duration = dur
            self.real_duration = dur
            self.modwheel = modwheel

        def __repr__(self):
            return '<DE %s P:%f A:%f D:%f W:%f>'%(MergeEvent.__repr__(self), self.pitch, self.ampl, self.duration, self.modwheel)

    class NoteStream(object):
        __slots__ = ['history', 'active', 'bentpitch', 'modwheel', 'prevparent']
        def __init__(self):
            self.history = []
            self.active = None
            self.bentpitch = None
            self.modwheel = 0
            self.prevparent = None
        def IsActive(self):
            return self.active is not None
        def Activate(self, mev, bentpitch=None, modwheel=None, parent=None):
            if bentpitch is None:
                bentpitch = mev.ev.pitch
            self.active = mev
            self.bentpitch = bentpitch
            if modwheel is not None:
                self.modwheel = modwheel
            self.prevparent = parent
        def Deactivate(self, mev):
            self.history.append(DurationEvent(self.active, self.bentpitch, self.active.ev.velocity / 127.0, mev.abstime - self.active.abstime, self.modwheel, self.prevparent))
            self.active = None
            self.bentpitch = None
            self.modwheel = 0
            self.prevparent = None
        def WouldDeactivate(self, mev):
            if not self.IsActive():
                return False
            if isinstance(mev.ev, midi.NoteOffEvent):
                return mev.ev.pitch == self.active.ev.pitch and mev.tidx == self.active.tidx and mev.ev.channel == self.active.ev.channel
            if isinstance(mev.ev, midi.PitchWheelEvent):
                return mev.tidx == self.active.tidx and mev.ev.channel == self.active.ev.channel
            if isinstance(mev.ev, midi.ControlChangeEvent):
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
    textstream = []

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
        if isinstance(mev.ev, midi.MetaEventWithText):
            textstream.append(mev)
        elif isinstance(mev.ev, midi.NoteOnEvent):
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
            found = False
            for group in notegroups:
                for stream in group.streams:
                    if stream.WouldDeactivate(mev):
                        old = stream.active
                        base = old.copy(abstime=mev.abstime)
                        stream.Deactivate(mev)
                        stream.Activate(base, base.ev.pitch + options.deviation * (mev.ev.pitch / float(0x2000)), parent=old)
                        found = True
            if not found:
                print 'WARNING: Did not find any matching active streams for %r'%(mev,)
                if options.verbose:
                    print '  Current state:'
                    for group in notegroups:
                        print '    Group %r:'%(group.name,)
                        for stream in group.streams:
                            print '      Stream: %r'%(stream.active,)
        elif options.modres > 0 and isinstance(mev.ev, midi.ControlChangeEvent):
            found = False
            for group in notegroups:
                for stream in group.streams:
                    if stream.WouldDeactivate(mev):
                        old = stream.active
                        base = old.copy(abstime=mev.abstime)
                        stream.Deactivate(mev)
                        stream.Activate(base, stream.bentpitch, mev.mw, parent=old)
                        found = True
            if not found:
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
                ns.Deactivate(MergeEvent(ns.active, ns.active.tidx, lastabstime))

    if options.slack > 0:
        print 'Adding slack time...'

        slack_evs = []
        for group in notegroups:
            for ns in group.streams:
                for dev in ns.history:
                    dev.duration += options.slack
                    slack_evs.append(dev)

        print 'Resorting all streams...'
        for group in notegroups:
            group.streams = []

        for dev in slack_evs:
            for group in notegroups:
                if not group.filter(dev):
                    continue
                for ns in group.streams:
                    if dev.abstime >= ns.history[-1].abstime + ns.history[-1].duration:
                        ns.history.append(dev)
                        break
                else:
                    group.streams.append(NoteStream())
                    group.streams[-1].history.append(dev)
                break
            else:
                print 'WARNING: No stream accepts event', dev

    if options.modres > 0:
        print 'Resolving modwheel events...'
        ev_cnt = 0
        for group in notegroups:
            for ns in group.streams:
                i = 0
                while i < len(ns.history):
                    dev = ns.history[i]
                    if dev.modwheel > 0:
                        realpitch = dev.pitch
                        realamp = dev.ampl
                        mwamp = float(dev.modwheel) / 0x3FFF
                        dt = 0.0
                        origtime = dev.abstime
                        events = []
                        while dt < dev.duration:
                            dev.abstime = origtime + dt
                            if options.modcont:
                                t = origtime
                            else:
                                t = dt
                            events.append(DurationEvent(dev, realpitch + mwamp * options.modfdev * math.sin(2 * math.pi * options.modffreq * t), realamp + mwamp * options.modadev * (math.sin(2 * math.pi * options.modafreq * t) - 1.0) / 2.0, min(options.modres, dev.duration - dt), dev.modwheel, dev))
                            dt += options.modres
                        ns.history[i:i+1] = events
                        i += len(events)
                        ev_cnt += len(events)
                        if options.verbose:
                            print 'Event', i, 'note', dev, 'in group', group.name, 'resolved to', len(events), 'events'
                            if options.debug:
                                for ev in events:
                                    print '\t', ev
                    else:
                        i += 1
        print '...resolved', ev_cnt, 'events'

    if options.stringres:
        print 'Resolving string models...'
        st_cnt = sum(sum(len(ns.history) for ns in group.streams) for group in notegroups)
        in_cnt = 0
        ex_cnt = 0
        ev_cnt = 0
        dev_grps = []
        for group in notegroups:
            for ns in group.streams:
                i = 0
                while i < len(ns.history):
                    dev = ns.history[i]
                    ntime = float('inf')
                    if i + 1 < len(ns.history):
                        ntime = ns.history[i+1].abstime
                    dt = 0.0
                    ampf = 1.0
                    origtime = dev.abstime
                    events = []
                    while dt < dev.duration and ampf * dev.ampl >= options.stringthres:
                        dev.abstime = origtime + dt
                        events.append(DurationEvent(dev, dev.pitch, ampf * dev.ampl, min(options.stringres, dev.duration - dt), dev.modwheel, dev))
                        if len(events) > options.stringmax:
                            print 'WARNING: Exceeded maximum string model events for event', i
                            if options.verbose:
                                print 'Final ampf', ampf, 'dt', dt
                            break
                        ampf *= options.stringrateon ** options.stringres
                        dt += options.stringres
                        in_cnt += 1
                    dt = dev.duration
                    while ampf * dev.ampl >= options.stringthres:
                        dev.abstime = origtime + dt
                        events.append(DurationEvent(dev, dev.pitch, ampf * dev.ampl, options.stringres, dev.modwheel, dev))
                        if len(events) > options.stringmax:
                            print 'WARNING: Exceeded maximum string model events for event', i
                            if options.verbose:
                                print 'Final ampf', ampf, 'dt', dt
                            break
                        ampf *= options.stringrateoff ** options.stringres
                        dt += options.stringres
                        ex_cnt += 1
                    if events:
                        for j in xrange(len(events) - 1):
                            cur, next = events[j], events[j + 1]
                            if abs(cur.abstime + cur.duration - next.abstime) > options.epsilon:
                                print 'WARNING: String model events cur: ', cur, 'next:', next, 'have gap/overrun of', next.abstime - (cur.abstime + cur.duration)
                        dev_grps.append(events)
                    else:
                        print 'WARNING: Event', i, 'note', dev, ': No events?'
                    if options.verbose:
                        print 'Event', i, 'note', dev, 'in group', group.name, 'resolved to', len(events), 'events'
                        if options.debug:
                            for ev in events:
                                print '\t', ev
                    i += 1
                    ev_cnt += len(events)
        print '...resolved', ev_cnt, 'events (+', ev_cnt - st_cnt, ',', in_cnt, 'inside', ex_cnt, 'extra), resorting streams...'
        for group in notegroups:
            group.streams = []

        dev_grps.sort(key = lambda evg: evg[0].abstime)
        for devgr in dev_grps:
            dev = devgr[0]
            for group in notegroups:
                if group.filter(dev):
                    grp = group
                    break
            else:
                grp = NSGroup()
                notegroups.append(grp)
            for ns in grp.streams:
                if not ns.history:
                    ns.history.extend(devgr)
                    break
                last = ns.history[-1]
                if dev.abstime >= last.abstime + last.duration - 1e-3:
                    ns.history.extend(devgr)
                    break
            else:
                ns = NoteStream()
                grp.streams.append(ns)
                ns.history.extend(devgr)
        scnt = 0
        for group in notegroups:
            for ns in group.streams:
                scnt += 1
        print 'Final sort:', len(notegroups), 'groups with', scnt, 'streams'

    if not options.keepempty:
        print 'Culling empty events...'
        ev_cnt = 0
        for group in notegroups:
            for ns in group.streams:
                i = 0
                while i < len(ns.history):
                    if ns.history[i].duration == 0.0:
                        del ns.history[i]
                        ev_cnt += 1
                    else:
                        i += 1
        print '...culled', ev_cnt, 'events'

    print 'Culling empty streams...'
    st_cnt = 0
    for group in notegroups:
        torem = set()
        for ns in group.streams:
            if not ns.history:
                torem.add(ns)
        st_cnt += len(torem)
        for rem in torem:
            group.streams.remove(rem)
    print '...culled', st_cnt, 'empty streams'

    if options.verbose:
        print 'Final group mappings:'
        for group in notegroups:
            print ('<anonymous>' if group.name is None else group.name), '<=', '(', len(group.streams), 'streams)'

    print 'Final volume resolution...'
    for group in notegroups:
        for ns in group.streams:
            for ev in ns.history:
                t, vol = sorted(filter(lambda pair: pair[0] <= ev.abstime, vol_at[ev.tidx][ev.ev.channel].items()), key=lambda pair: pair[0])[-1]
                ev.ampl *= (float(vol) / 0x3FFF) ** options.vol_pow

    print 'Checking consistency...'
    for group in notegroups:
        if options.verbose:
            print 'Group', '<None>' if group.name is None else group.name, 'with', len(group.streams), 'streams...',
        ecnt = 0
        for ns in group.streams:
            for i in xrange(len(ns.history) - 1):
                cur, next = ns.history[i], ns.history[i + 1]
                if cur.abstime + cur.duration > next.abstime + options.epsilon:
                    print 'WARNING: event', i, 'collides with next event (@', cur.abstime, '+', cur.duration, 'next @', next.abstime, ';', next.abstime - (cur.abstime + cur.duration), 'overlap)'
                    ecnt += 1
                if cur.abstime > next.abstime:
                    print 'WARNING: event', i + 1, 'out of sort order (@', cur.abstime, 'next @', next.abstime, ';', cur.abstime - next.abstime, 'underlap)'
                    ecnt += 1
        if options.verbose:
            if ecnt > 0:
                print '...', ecnt, 'errors occured'
            else:
                print 'ok'

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

    for group in notegroups:
            for ns in group.streams:
                    ivns = ET.SubElement(ivstreams, 'stream')
                    ivns.set('type', 'ns')
                    if group.name is not None:
                            ivns.set('group', group.name)
                    for note in ns.history:
                            ivnote = ET.SubElement(ivns, 'note', id=str(id(note)))
                            ivnote.set('pitch', str(note.pitch))
                            ivnote.set('vel', str(int(note.ampl * 127.0)))
                            ivnote.set('ampl', str(note.ampl))
                            ivnote.set('time', str(note.abstime))
                            ivnote.set('dur', str(note.real_duration))
                            if note.par:
                                ivnote.set('par', str(id(note.par)))

    if not options.no_text:
        ivtext = ET.SubElement(ivstreams, 'stream', type='text')
        for tev in textstream:
            text = tev.ev.text
            try:
                text = text.decode('utf8')
            except UnicodeDecodeError:
                text = 'base64:' + text.encode('base64')
            ivev = ET.SubElement(ivtext, 'text', time=str(tev.abstime), type=type(tev.ev).__name__, text=text)

    ivaux = ET.SubElement(ivstreams, 'stream')
    ivaux.set('type', 'aux')

    fw = midi.FileWriter()
    fw.RunningStatus = None # XXX Hack

    for mev in auxstream:
        ivev = ET.SubElement(ivaux, 'ev')
        ivev.set('time', str(mev.abstime))
        ivev.set('data', repr(fw.encode_midi_event(mev.ev)))

    ivargs = ET.SubElement(ivmeta, 'args')
    ivargs.text = ' '.join('%r' % (i,) for i in sys.argv[1:])

    ivapp = ET.SubElement(ivmeta, 'app')
    ivapp.text = 'mkiv'

    print 'Done.'
    txt = ET.tostring(iv, 'UTF-8')
    open(os.path.splitext(os.path.basename(fname))[0]+'.iv', 'wb').write(txt)
