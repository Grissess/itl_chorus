import socket
import sys
import struct
import time
import xml.etree.ElementTree as ET
import threading
import thread
import optparse
import random
import itertools
import re
import os

from packet import Packet, CMD, PLF, itos, OBLIGATE_POLYPHONE

parser = optparse.OptionParser()
parser.add_option('-t', '--test', dest='test', action='store_true', help='Play a test tone (440, 880) on all clients in sequence (the last overlaps with the first of the next)')
parser.add_option('-T', '--transpose', dest='transpose', type='int', help='Transpose by a set amount of semitones (positive or negative)')
parser.add_option('--sync-test', dest='sync_test', action='store_true', help='Don\'t wait for clients to play tones properly--have them all test tone at the same time')
parser.add_option('--wait-test', dest='wait_test', action='store_true', help='Wait for user input before moving to the next client tested')
parser.add_option('-R', '--random', dest='random', type='float', help='Generate random notes at approximately this period')
parser.add_option('--rand-low', dest='rand_low', type='int', help='Low frequency to randomly sample')
parser.add_option('--rand-high', dest='rand_high', type='int', help='High frequency to randomly sample')
parser.add_option('-l', '--live', dest='live', help='Enter live mode (play from a controller in real time), specifying the port to connect to as "client,port"; use just "," to manually subscribe later')
parser.add_option('-L', '--list-live', dest='list_live', action='store_true', help='List all the clients and ports that can be connected to for live performance')
parser.add_option('--no-sustain', dest='no_sustain', action='store_true', help='Don\'t use sustain hacks in live mode')
parser.add_option('-q', '--quit', dest='quit', action='store_true', help='Instruct all clients to quit')
parser.add_option('-p', '--play', dest='play', action='append', help='Play a single tone or chord (specified multiple times) on all listening clients (either "midi pitch" or "@frequency")')
parser.add_option('-P', '--play-async', dest='play_async', action='store_true', help='Don\'t wait for the tone to finish using the local clock')
parser.add_option('-D', '--duration', dest='duration', type='float', help='How long to play this note for')
parser.add_option('-V', '--volume', dest='volume', type='float', help='Master volume [0.0, 1.0]')
parser.add_option('-s', '--silence', dest='silence', action='store_true', help='Instruct all clients to stop playing any active tones')
parser.add_option('-S', '--seek', dest='seek', type='float', help='Start time in seconds (scaled by --factor)')
parser.add_option('-f', '--factor', dest='factor', type='float', help='Rescale time by this factor (0<f<1 are faster; 0.5 is twice the speed, 2 is half)')
parser.add_option('-c', '--clamp', dest='clamp', action='store_true', help='Clamp over-the-wire amplitudes to 0.0-1.0')
parser.add_option('-r', '--route', dest='routes', action='append', help='Add a routing directive (see --route-help)')
parser.add_option('--clear-routes', dest='routes', action='store_const', const=[], help='Clear routes previously specified (including the default)')
parser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Be verbose; dump events and actual time (can slow down performance!)')
parser.add_option('-W', '--wait-time', dest='wait_time', type='float', help='How long to wait between pings for clients to initially respond (delays all broadcasts)')
parser.add_option('--tries', dest='tries', type='int', help='Number of ping packets to send')
parser.add_option('-B', '--bind-addr', dest='bind_addr', help='The IP address (or IP:port) to bind to (influences the network to send to)')
parser.add_option('--to', dest='to', action='append', help='IP:port pairs to send to (skips discovery)')
parser.add_option('--port', dest='ports', action='append', type='int', help='Add a port to find clients on')
parser.add_option('--clear-ports', dest='ports', action='store_const', const=[], help='Clear ports previously specified (including the default)')
parser.add_option('--repeat', dest='repeat', action='store_true', help='Repeat the file playlist indefinitely')
parser.add_option('-n', '--number', dest='number', type='int', help='Number of clients to use; if negative (default -1), use the product of stream count and the absolute value of this parameter')
parser.add_option('--dry', dest='dry', action='store_true', help='Dry run--don\'t actually search for or play to clients, but pretend they exist (useful with -G)')
parser.add_option('--pcm', dest='pcm', action='store_true', help='Use experimental PCM rendering')
parser.add_option('--pcm-lead', dest='pcmlead', type='float', help='Seconds of leading PCM data to send')
parser.add_option('--pcm-sync-every', dest='pcm_sync_every', type='int', help='How many PCM packets to wait before sending a SYNC event with buffer amounts')
parser.add_option('--spin', dest='spin', action='store_true', help='Ignore delta times in the queue (busy loop the CPU) for higher accuracy')
parser.add_option('--tapper', dest='tapper', type='float', help='When the main loop would wait this many seconds, wait instead for a keypress')
parser.add_option('-G', '--gui', dest='gui', default='', help='set a GUI to use')
parser.add_option('--pg-fullscreen', dest='fullscreen', action='store_true', help='Use a full-screen video mode')
parser.add_option('--pg-width', dest='pg_width', type='int', help='Width of the pygame window')
parser.add_option('--pg-height', dest='pg_height', type='int', help='Width of the pygame window')
parser.add_option('--help-routes', dest='help_routes', action='store_true', help='Show help about routing directives')
parser.set_defaults(routes=['T:DRUM=!perc,0'], random=0.0, rand_low=80, rand_high=2000, live=None, factor=1.0, duration=0.25, volume=1.0, wait_time=0.1, tries=5, play=[], transpose=0, seek=0.0, bind_addr='', to=[], ports=[13676, 13677], tapper=None, pg_width = 0, pg_height = 0, number=-1, pcmlead=0.1, pcm_sync_every=4096)
options, args = parser.parse_args()

tap_func = None
play_time = time.time
if options.tapper is not None:
    tap_play_time = 0.0
    play_time = lambda: tap_play_time
    if sys.platform.startswith('win'):
        import msvcrt

        tap_func = msvcrt.getch

    else:
        import termios, tty

# https://stackoverflow.com/questions/1052107/reading-a-single-character-getch-style-in-python-is-not-working-in-unix
        def unix_tap_func():
            fd = sys.stdin.fileno()  # 0?
            prev_settings = termios.tcgetattr(fd)
            try:
                mode = prev_settings[:]
                mode[tty.LFLAG] &= ~(termios.ECHO | termios.ICANON)
                termios.tcsetattr(fd, termios.TCSAFLUSH, mode)
                return sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, prev_settings)

        tap_func = unix_tap_func

if options.help_routes:
    print '''Routes are a way of either exclusively or mutually binding certain streams to certain playback clients. They are especially fitting in heterogenous environments where some clients will outperform others in certain pitches or with certain parts.

Routes are fully specified by:
-The attribute to be routed on (either type "T", or UID "U")
-The value of that attribute
-The exclusivity of that route ("+" for inclusive, "-" for exclusive, "!" for complete)
-The stream group to be routed there, or 0 to null route.
The first two may be replaced by a single '0' to null route a stream--effective only when used with an exclusive route.

"Complete" exclusivity is valid only for obligate polyphones, and indicates that *all* matches are to receive the stream. In other cases, this will have the undesirable effect of routing only one stream.

The special group ALL matches all streams. Regular expressions may be used to specify groups. Note that the first character is *not* part of the regular expression.

The syntax for that specification resembles the following:

    broadcast.py -r U:bass=+bass -r U:treble1,U:treble2=+treble -r T:BEEP=-beeps,-trk3,-trk5 -r U:noise=0

The specifier consists of a comma-separated list of attribute-colon-value pairs, followed by an equal sign. After this is a comma-separated list of exclusivities paired with the name of a stream group as specified in the file. The above example shows that stream groups "bass", "treble", and "beeps" will be routed to clients with UID "bass", "treble", and TYPE "BEEP" respectively. Additionally, TYPE "BEEP" will receive tracks 4 and 6 (indices 3 and 5) of the MIDI file (presumably split with -T), and that these three groups are exclusively to be routed to TYPE "BEEP" clients only (the broadcaster will drop the stream if no more are available), as opposed to the preference of the bass and treble groups, which may be routed onto other stream clients if they are available. Finally, the last route says that all "noise" UID clients should not proceed any further (receiving "null" streams) instead. Order is important; if a "noise" client already received a stream (such as "+beeps"), then it would receive that route with priority.'''
    exit()

GUIS = {}
BASETIME = play_time()  # XXX fixes a race with the GUI
factor = options.factor

def gui_pygame():
    # XXX Racy, do this fast
    global tap_func, BASETIME, factor
    key_cond = threading.Condition()
    if options.tapper is not None:

        def pygame_tap_func():
            with key_cond:
                key_cond.wait()

        tap_func = pygame_tap_func

    print 'Starting pygame GUI...'
    import pygame, colorsys
    pygame.init()
    print 'Pygame init'

    dispinfo = pygame.display.Info()
    DISP_WIDTH = 640
    DISP_HEIGHT = 480
    if dispinfo.current_h > 0 and dispinfo.current_w > 0:
        DISP_WIDTH = dispinfo.current_w
        DISP_HEIGHT = dispinfo.current_h
    print 'Pygame info'

    WIDTH = DISP_WIDTH
    if options.pg_width > 0:
        WIDTH = options.pg_width
    HEIGHT = DISP_HEIGHT
    if options.pg_height > 0:
        HEIGHT = options.pg_height

    flags = 0
    if options.fullscreen:
        flags |= pygame.FULLSCREEN

    disp = pygame.display.set_mode((WIDTH, HEIGHT), flags)
    print 'Disp acquire'

    PFAC = HEIGHT / 128.0

    clock = pygame.time.Clock()
    font = pygame.font.SysFont(pygame.font.get_default_font(), 24)
    status = ('', 0.0)
    DISP_TIME = 4.0

    print 'Pygame GUI initialized, running...'

    while True:

        disp.scroll(-1, 0)
        disp.fill((0, 0, 0), (WIDTH - 1, 0, 1, HEIGHT))
        idx = 0
        for cli, note in sorted(playing_notes.items(), key = lambda pair: pair[0]):
            pitch = note[0]
            col = colorsys.hls_to_rgb(float(idx) / len(targets), note[1]/2.0, 1.0)
            col = [min(max(int(i*255), 0), 255) for i in col]
            disp.fill(col, (WIDTH - 1, HEIGHT - pitch * PFAC - PFAC, 1, PFAC))
            idx += 1
        tsurf = font.render('%0.3f' % ((play_time() - BASETIME) / factor,), True, (255, 255, 255), (0, 0, 0))
        disp.fill((0, 0, 0), tsurf.get_rect())
        disp.blit(tsurf, (0, 0))
        if time.time() - DISP_TIME < status[1]:
            ssurf = font.render(status[0], True, (0, 255, 0), (0, 0, 0))
            disp.blit(ssurf, (0, tsurf.get_height()))
        pygame.display.flip()

        for ev in pygame.event.get():
            if ev.type == pygame.KEYDOWN:
                with key_cond:
                    key_cond.notify()
                if ev.key == pygame.K_ESCAPE:
                    thread.interrupt_main()
                    pygame.quit()
                    exit()
                elif ev.key == pygame.K_LEFT:
                    BASETIME += 5
                elif ev.key == pygame.K_RIGHT:
                    BASETIME -= 5
                elif ev.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
                    pt = play_time()
                    rtime = (pt - BASETIME) / factor
                    if ev.key == pygame.K_LEFTBRACKET:
                        factor /= 1.1
                    elif ev.key == pygame.K_RIGHTBRACKET:
                        factor *= 1.1
                    BASETIME = pt - rtime * factor
                    status = ('factor: ' + str(factor), time.time())

        clock.tick(60)

GUIS['pygame'] = gui_pygame

print 'Factor:', factor

try:
    rows, columns = map(int, os.popen('stty size', 'r').read().split())
except Exception:
    import traceback
    traceback.print_exc()
    rows, columns = 25, 80

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
if options.bind_addr:
    addr, _, port = options.bind_addr.partition(':')
    if not port:
        port = '12074'
    s.bind((addr, int(port)))

clients = set()
targets = set()
uid_groups = {}
type_groups = {}
ports = {}

s.settimeout(options.wait_time)

if options.to:
    for dst in options.to:
        host, _, port = dst.partition(':')
        clients.add((host, int(port)))
else:
    if not options.dry:
        for PORT in options.ports:
            for num in xrange(options.tries):
                s.sendto(str(Packet(CMD.PING)), ('255.255.255.255', PORT))
                try:
                    while True:
                        data, src = s.recvfrom(4096)
                        clients.add(src)
                except socket.timeout:
                    pass

print len(clients), 'detected clients'

for num in xrange(options.tries):
    print 'Try', num
    for cl in clients:
	print cl,
        s.sendto(str(Packet(CMD.CAPS)), cl)
        data, _ = s.recvfrom(4096)
        pkt = Packet.FromStr(data)
        print 'ports', pkt.data[0],
        ports[cl] = pkt.data[0]
        tp = itos(pkt.data[1])
        print 'type', tp,
        uid = ''.join([itos(i) for i in pkt.data[2:]]).rstrip('\x00')
        print 'uid', uid
        if uid == '':
            uid = None
        uid_groups.setdefault(uid, set()).add(cl)
        type_groups.setdefault(tp, set()).add(cl)
	if options.test:
            ts, tms = int(options.duration), int(options.duration * 1000000) % 1000000
            if options.wait_test:
                s.sendto(str(Packet(CMD.PLAY, 65535, 0, 440, options.volume)), cl)
                raw_input('%r: Press enter to test next client...' %(cl,))
                s.sendto(str(Packet(CMD.PLAY, ts, tms, 880, options.volume)), cl)
            else:
                s.sendto(str(Packet(CMD.PLAY, ts, tms, 440, options.volume)), cl)
                if not options.sync_test:
                    time.sleep(options.duration)
                    s.sendto(str(Packet(CMD.PLAY, ts, tms, 880, options.volume)), cl)
	if options.quit:
		s.sendto(str(Packet(CMD.QUIT)), cl)
        if options.silence:
            for i in xrange(pkt.data[0]):
                s.sendto(str(Packet(CMD.PLAY, 0, 0, 0, 0.0, i)), cl)
        if pkt.data[0] == OBLIGATE_POLYPHONE:
            pkt.data[0] = 1
        for i in xrange(pkt.data[0]):
            targets.add(cl+(i,))

playing_notes = {}
for tg in targets:
    playing_notes[tg] = (0, 0)

if options.gui:
    gui_thr = threading.Thread(target=GUIS[options.gui], args=())
    gui_thr.setDaemon(True)
    gui_thr.start()

if options.play:
    for i, val in enumerate(options.play):
        if val.startswith('@'):
            options.play[i] = int(val[1:])
        else:
            options.play[i] = int(440.0 * 2**((int(val) - 69)/12.0))
    for i, cl in enumerate(targets):
        s.sendto(str(Packet(CMD.PLAY, int(options.duration), int(1000000*(options.duration-int(options.duration))), options.play[i%len(options.play)], options.volume, cl[2])), cl[:2])
    if not options.play_async:
        time.sleep(options.duration)
    exit()

if options.test and options.sync_test:
    time.sleep(0.25)
    for cl in targets:
        s.sendto(str(Packet(CMD.PLAY, 0, 250000, 880, options.volume, cl[2])), cl[:2])

if options.test or options.quit or options.silence:
    print uid_groups
    print type_groups
    exit()

if options.random > 0:
    while True:
        for cl in targets:
            s.sendto(str(Packet(CMD.PLAY, int(options.random), int(1000000*(options.random-int(options.random))), random.randint(options.rand_low, options.rand_high), options.volume, cl[2])), cl[:2])
        time.sleep(options.random)

if options.live or options.list_live:
    if options.gui:
        print 'Waiting a second for GUI init...'
        time.sleep(3.0)
    import midi
    from midi import sequencer
    S = sequencer.S
    if options.list_live:
        print sequencer.SequencerHardware()
        exit()
    seq = sequencer.SequencerRead(sequencer_resolution=120)
    client_set = set(targets)
    active_set = {} # note (pitch) -> [client]
    deferred_set = set() # pitches held due to sustain
    sustain_status = False
    client, _, port = options.live.partition(',')
    if client or port:
        seq.subscribe_port(client, port)
    seq.start_sequencer()
    if not options.gui:  # FIXME
        seq.set_nonblock(False)
    while True:
        ev = S.event_input(seq.client)
        if ev is None:
            time.sleep(0)
        event = None
        if ev:
            if options.verbose:
                print 'SEQ:', ev
            if ev < 0:
                seq._error(ev)
            if ev.type == S.SND_SEQ_EVENT_NOTEON:
                event = midi.NoteOnEvent(channel = ev.data.note.channel, pitch = ev.data.note.note, velocity = ev.data.note.velocity)
            elif ev.type == S.SND_SEQ_EVENT_NOTEOFF:
                event = midi.NoteOffEvent(channel = ev.data.note.channel, pitch = ev.data.note.note, velocity = ev.data.note.velocity)
            elif ev.type == S.SND_SEQ_EVENT_CONTROLLER:
                event = midi.ControlChangeEvent(channel = ev.data.control.channel, control = ev.data.control.param, value = ev.data.control.value)
            elif ev.type == S.SND_SEQ_EVENT_PGMCHANGE:
                event = midi.ProgramChangeEvent(channel = ev.data.control.channel, value = ev.data.control.value)
            elif ev.type == S.SND_SEQ_EVENT_PITCHBEND:
                event = midi.PitchWheelEvent(channel = ev.data.control.channel, pitch = ev.data.control.value)
            elif options.verbose:
                print 'WARNING: Unparsed event, type %r'%(ev.type,)
                continue
        if event is not None:
            if isinstance(event, midi.NoteOnEvent) and event.velocity == 0:
                event.__class__ = midi.NoteOffEvent
            if options.verbose:
                print 'EVENT:', event
            if isinstance(event, midi.NoteOnEvent):
                if event.pitch in active_set:
                    if sustain_status:
                        deferred_set.discard(event.pitch)
                inactive_set = client_set - set(sum(active_set.values(), []))
                if not inactive_set:
                    print 'WARNING: Out of clients to do note %r; dropped'%(event.pitch,)
                    continue
                cli = sorted(inactive_set)[0]
                s.sendto(str(Packet(CMD.PLAY, 65535, 0, int(440.0 * 2**((event.pitch-69)/12.0)), event.velocity / 127.0, cli[2])), cli[:2])
                active_set.setdefault(event.pitch, []).append(cli)
                playing_notes[cli] = (event.pitch, event.velocity / 127.0)
                if options.verbose:
                    print 'LIVE:', event.pitch, '+ =>', active_set[event.pitch]
            elif isinstance(event, midi.NoteOffEvent):
                if event.pitch not in active_set or not active_set[event.pitch]:
                    print 'WARNING: Deactivating inactive note %r'%(event.pitch,)
                    continue
                if sustain_status:
                    deferred_set.add(event.pitch)
                    continue
                cli = active_set[event.pitch].pop()
                s.sendto(str(Packet(CMD.PLAY, 0, 1, 1, 0, cli[2])), cli[:2])
                playing_notes[cli] = (0, 0)
                if options.verbose:
                    print 'LIVE:', event.pitch, '- =>', active_set[event.pitch]
                    if sustain_status:
                        print '...ignored (sustain on)'
            elif isinstance(event, midi.ControlChangeEvent):
                if event.control == 64 and not options.no_sustain:
                    sustain_status = (event.value >= 64)
                    if options.verbose:
                        print 'LIVE: SUSTAIN', ('+' if sustain_status else '-')
                    if not sustain_status:
                        for pitch in deferred_set:
                            if pitch not in active_set or not active_set[pitch]:
                                print 'WARNING: Attempted deferred removal of inactive note %r'%(pitch,)
                                continue
                            for cli in active_set[pitch]:
                                s.sendto(str(Packet(CMD.PLAY, 0, 1, 1, 0, cli[2])), cli[:2])
                                playing_notes[cli] = (0, 0)
                            del active_set[pitch]
                        deferred_set.clear()

if options.repeat:
    args = itertools.cycle(args)

for fname in args:
    if options.pcm and not fname.endswith('.iv'):
        print 'PCM: play', fname
        if fname == '-':
            import wave
            pcr = wave.open(sys.stdin)
            samprate = pcr.getframerate()
            pcr.read = pcr.readframes
        else:
            try:
                import audiotools
                pcr = audiotools.open(fname).to_pcm()
                assert pcr.channels == 1 and pcr.bits_per_sample == 16 and pcr.sample_rate == 44100
                samprate = pcr.sample_rate
            except ImportError:
                import wave
                pcr = wave.open(fname, 'r')
                assert pcr.getnchannels() == 1 and pcr.getsampwidth() == 2 and pcr.getframerate() == 44100
                samprate = pcr.getframerate()
                pcr.read = pcr.readframes

        def read_all(fn, n):
            buf = ''
            while len(buf) < n:
                nbuf = fn.read(n - len(buf))
                if not isinstance(nbuf, str):
                    nbuf = nbuf.to_bytes(False, True)
                buf += nbuf
            return buf

        BASETIME = play_time() - options.pcmlead
        sampcnt = 0
        buf = read_all(pcr, 32)
        pcnt = 0
        print 'PCM: pcr', pcr, 'BASETIME', BASETIME, 'buf', len(buf)
        while len(buf) >= 32:
            frag = buf[:32]
            buf = buf[32:]
            for cl in clients:
                s.sendto(struct.pack('>L', CMD.PCM) + frag, cl)
            pcnt += 1
            if pcnt >= options.pcm_sync_every:
                for cl in clients:
                    s.sendto(str(Packet(CMD.PCMSYN, int(options.pcmlead * samprate))), cl)
                print 'PCMSYN'
                pcnt = 0
            sampcnt += len(frag) / 2
            delay = max(0, BASETIME + (sampcnt / float(samprate)) - play_time())
            #print sampcnt, delay
            if delay > 0:
                time.sleep(delay)
            if len(buf) < 32:
                buf += read_all(pcr, 32 - len(buf))
        print 'PCM: exit'
        continue
    try:
        if fname.endswith('.ivz'):
            import gzip
            ivf = gzip.open(fname, 'rb')
        elif fname.endswith('.ivb'):
            import bz2
            ivf = bz2.BZ2File(fname, 'r')
        else:
            ivf = open(fname, 'rb')
        iv = ET.parse(ivf).getroot()
    except IOError:
        import traceback
        traceback.print_exc()
        print fname, ': Bad file'
        continue

    notestreams = iv.findall("./streams/stream[@type='ns']")
    groups = set([ns.get('group') for ns in notestreams if 'group' in ns.keys()])
    number = (len(notestreams) * abs(options.number) if options.number < 0 else options.number)
    print len(notestreams), 'notestreams'
    print len(clients), 'clients'
    print len(targets), 'targets'
    print len(groups), 'groups'
    print number, 'clients used (number)'

    class Route(object):
        def __init__(self, fattr, fvalue, group, excl=False, complete=False):
            if fattr == 'U':
                self.map = uid_groups
            elif fattr == 'T':
                self.map = type_groups
            elif fattr == '0':
                self.map = {}
            else:
                raise ValueError('Not a valid attribute specifier: %r'%(fattr,))
            self.value = fvalue
            self.group = group
            self.excl = excl
            self.complete = complete
        @classmethod
        def Parse(cls, s):
            fspecs, _, grpspecs = map(lambda x: x.strip(), s.partition('='))
            fpairs = []
            ret = []
            for fspec in [i.strip() for i in fspecs.split(',')]:
                fattr, _, fvalue = map(lambda x: x.strip(), fspec.partition(':'))
                fpairs.append((fattr, fvalue))
            for part in [i.strip() for i in grpspecs.split(',')]:
                for fattr, fvalue in fpairs:
                    if part[0] == '+':
                        ret.append(Route(fattr, fvalue, part[1:], False))
                    elif part[0] == '-':
                        ret.append(Route(fattr, fvalue, part[1:], True))
                    elif part[0] == '!':
                        ret.append(Route(fattr, fvalue, part[1:], True, True))
                    elif part[0] == '0':
                        ret.append(Route(fattr, fvalue, None, True))
                    else:
                        raise ValueError('Not an exclusivity: %r'%(part[0],))
            return ret
        def Apply(self, cli):
            return cli[:2] in self.map.get(self.value, [])
        def __repr__(self):
            return '<Route of %r to %s:%s>'%(self.group, ('U' if self.map is uid_groups else 'T'), self.value)

    class RouteSet(object):
        def __init__(self, clis=None):
            if clis is None:
                clis = set(targets)
            self.clients = list(clis)
            self.routes = []
        def Route(self, stream):
            testset = self.clients
            grp = stream.get('group', 'ALL')
            if options.verbose:
                print 'Routing', grp, '...'
            excl = False
            for route in self.routes:
                if route.group is not None and re.match(route.group, grp) is not None:
                    if options.verbose:
                        print '\tMatches route', route
                    excl = excl or route.excl
                    matches = filter(lambda x, route=route: route.Apply(x), testset)
                    if matches:
                        if route.complete:
                            if options.verbose:
                                print '\tUsing ALL clients:', matches
                            for cl in matches:
                                self.clients.remove(matches[0])
                                if ports.get(matches[0][:2]) == OBLIGATE_POLYPHONE:
                                    self.clients.append(matches[0])
                            return matches
                        if options.verbose:
                            print '\tUsing client', matches[0]
                        self.clients.remove(matches[0])
                        if ports.get(matches[0][:2]) == OBLIGATE_POLYPHONE:
                            self.clients.append(matches[0])
                        return [matches[0]]
                    if options.verbose:
                        print '\tNo matches, moving on...'
                if route.group is None:
                    if options.verbose:
                        print 'Encountered NULL route, removing from search space...'
                    toremove = []
                    for cli in testset:
                        if route.Apply(cli):
                            toremove.append(cli)
                    for cli in toremove:
                        if options.verbose:
                            print '\tRemoving', cli, '...'
                        testset.remove(cli)
            if excl:
                if options.verbose:
                    print '\tExclusively routed, no route matched.'
                return []
            if not testset:
                if options.verbose:
                    print '\tOut of clients, no route matched.'
                return []
            cli = list(testset)[0]
            self.clients.remove(cli)
            if ports.get(cli[:2]) == OBLIGATE_POLYPHONE:
                self.clients.append(cli)
            if options.verbose:
                print '\tDefault route to', cli
            return [cli]

    routeset = RouteSet()
    for rspec in options.routes:
        try:
            routeset.routes.extend(Route.Parse(rspec))
        except Exception:
            import traceback
            traceback.print_exc()

    if options.verbose:
        print 'All routes:'
        for route in routeset.routes:
            print route

    class NSThread(threading.Thread):
            def __init__(self, *args, **kwargs):
                threading.Thread.__init__(self, *args, **kwargs)
                self.done = False
                self.cur_offt = None
                self.next_t = None
            def actuate_missed(self):
                nsq, cls = self._Thread__args
                dur = None
                i = 0
                while nsq and float(nsq[0].get('time'))*factor <= play_time() - BASETIME:
                    i += 1
                    note = nsq.pop(0)
                    ttime = float(note.get('time'))
                    if note.tag == 'art':
                        val = float(note.get('value'))
                        idx = int(note.get('index'))
                        global_ = note.get('global') is not None
                        if not options.dry:
                            for cl in cls:
                                s.sendto(str(Packet(CMD.ARTP, OBLIGATE_POLYPHONE if global_ else cl[2], idx, val)), cl[:2])
                        if options.verbose:
                            print (play_time() - BASETIME), cl, ': ARTP', cl[2], idx, val
                        continue
                    pitch = float(note.get('pitch')) + options.transpose
                    ampl = float(note.get('ampl', float(note.get('vel', 127.0)) / 127.0))
                    dur = factor*float(note.get('dur'))
                    pl_dur = dur if options.tapper is None else 65535
                    if options.verbose:
                        print (play_time() - BASETIME) / options.factor, ': PLAY', pitch, dur, ampl
                    if options.dry:
                        playing_notes[self.nsid] = (pitch, ampl)
                    else:
                        amp = ampl * options.volume
                        if options.clamp:
                            amp = max(min(amp, 1.0), 0.0)
                        flags = 0
                        if note.get('par', None):
                            flags |= PLF.SAMEPHASE
                        for cl in cls:
                            s.sendto(str(Packet(CMD.PLAY, int(pl_dur), int((pl_dur*1000000)%1000000), int(440.0 * 2**((pitch-69)/12.0)), amp, cl[2], flags)), cl[:2])
                            playing_notes[cl] = (pitch, ampl)
                if i > 0 and dur is not None:
                    self.cur_offt = ttime + dur / options.factor
                else:
                    if self.cur_offt:
                        if factor * self.cur_offt <= play_time() - BASETIME:
                            if options.verbose:
                                print '% 6.5f'%((play_time() - BASETIME) / factor,), ': DONE'
                            if options.tapper is not None:
                                for cl in cls:
                                    s.sendto(str(Packet(CMD.PLAY, 0, 1, 1, 0.0, cl[2])), cl[:2])
                            self.cur_offt = None
                            if options.dry:
                                playing_notes[self.nsid] = (0, 0)
                            else:
                                for cl in cls:
                                    playing_notes[cl] = (0, 0)
                next_act = None
                if nsq:
                    next_act = float(nsq[0].get('time'))
                if options.verbose:
                    print 'NEXT_ACT:', next_act, 'CUR_OFFT:', self.cur_offt
                self.next_t = min((next_act or float('inf'), self.cur_offt or float('inf')))
                self.done = not (nsq or self.cur_offt)
            def drop_missed(self):
                nsq, cl = self._Thread__args
                cnt = 0
                while nsq and float(nsq[0].get('time'))*factor < play_time() - BASETIME:
                    nsq.pop(0)
                    cnt += 1
                if options.verbose:
                    print self, 'dropped', cnt, 'notes due to miss'
            def wait_for(self, t):
                if t <= 0:
                    return
                time.sleep(t)
            def run(self):
                    nsq, cls = self._Thread__args
                    for note in nsq:
                            ttime = float(note.get('time'))
                            if note.tag == 'art':
                                val = float(note.get('value'))
                                idx = int(note.get('index'))
                                global_ = note.get('global') is not None
                                if not options.dry:
                                    for cl in cls:
                                        s.sendto(str(Packet(CMD.ARTP, OBLIGATE_POLYPHONE if global_ else cl[2], idx, val)), cl[:2])
                                if options.verbose:
                                    print (play_time() - BASETIME), cl, ': ARTP', cl[2], idx, val
                                continue
                            pitch = float(note.get('pitch')) + options.transpose
                            ampl = float(note.get('ampl', float(note.get('vel', 127.0)) / 127.0))
                            dur = factor*float(note.get('dur'))
                            while play_time() - BASETIME < factor*ttime:
                                self.wait_for(factor*ttime - (play_time() - BASETIME))
                            if options.dry:
                                cl = self.nsid  # XXX hack
                            else:
                                for cl in cls:
                                    s.sendto(str(Packet(CMD.PLAY, int(dur), int((dur*1000000)%1000000), int(440.0 * 2**((pitch-69)/12.0)), ampl * options.volume, cl[2])), cl[:2])
                            if options.verbose:
                                print (play_time() - BASETIME), cl, ': PLAY', pitch, dur, vel
                            playing_notes[cl] = (pitch, ampl)
                            self.wait_for(dur - ((play_time() - BASETIME) - factor*ttime))
                            playing_notes[cl] = (0, 0)
                    if options.verbose:
                        print '% 6.5f'%(play_time() - BASETIME,), cl, ': DONE'

    threads = {}
    if options.dry:
        for nsid, ns in enumerate(notestreams):
            nsq = ns.findall('note')
            nsq.sort(key=lambda x: float(x.get('time')))
            threads[ns] = NSThread(args=(nsq, set()))
            threads[ns].nsid = nsid
        targets = threads.values()  # XXX hack
    else:
        nscycle = itertools.cycle(notestreams)
        for idx, ns in zip(xrange(number), nscycle):
            clis = routeset.Route(ns)
            for cli in clis:
                nsq = ns.findall('*')
                nsq.sort(key=lambda x: float(x.get('time')))
                if ns in threads:
                    threads[ns]._Thread__args[1].add(cli)
                else:
                    threads[ns] = NSThread(args=(nsq, set([cli])))

    if options.verbose:
        print 'Playback threads:'
        for thr in threads.values():
            print thr._Thread__args[1]

    BASETIME = play_time() - (options.seek*factor)
    ENDTIME = max(max(float(n.get('time', 0.0)) + float(n.get('dur', 0.0)) for n in thr._Thread__args[0]) for thr in threads.values())
    print 'Playtime is', ENDTIME
    if options.seek > 0:
        for thr in threads.values():
            thr.drop_missed()
    spin_phase = 0
    SPINNERS = ['-', '\\', '|', '/']
    while not all(thr.done for thr in threads.values()):
        for thr in threads.values():
            if thr.next_t is None or factor * thr.next_t <= play_time() - BASETIME:
                thr.actuate_missed()
        delta = factor * min(thr.next_t for thr in threads.values() if thr.next_t is not None) + BASETIME - play_time()
        if delta == float('inf'):
            print 'WARNING: Infinite postponement detected! Did all notestreams finish?'
            break
        if options.verbose:
            print 'TICK DELTA:', delta
        else:
            sys.stdout.write('\x1b[G\x1b[K[%s]' % (
                ('#' * int((play_time() - BASETIME) * (columns - 2) / (ENDTIME * factor)) + SPINNERS[spin_phase]).ljust(columns - 2),
            ))
            sys.stdout.flush()
            spin_phase += 1
            if spin_phase >= len(SPINNERS):
                spin_phase = 0
        if delta >= 0 and not options.spin:
            if tap_func is not None:
                try:
                    delta_on = factor * min(thr.next_t for thr in threads.values() if thr.next_t is not None and thr.next_t != thr.cur_offt)
                except ValueError:
                    delta_on = float('inf')
                if delta_on >= options.tapper:
                    if options.verbose:
                        print 'TAP'
                    tap_func()
                else:
                    time.sleep(delta)
                tap_play_time += delta
            else:
                time.sleep(delta)
    print fname, ': Done!'
