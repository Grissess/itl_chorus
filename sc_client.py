import argparse, socket, threading, time, random, shlex

from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

from packet import Packet, CMD, PLF, stoi, OBLIGATE_POLYPHONE

class CustomArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(CustomArgumentParser, self).__init__(
                description = 'ITL Chorus SuperCollider Client',
                fromfile_prefix_chars = '@',
                epilog = 'Use at-sign (@) prefixing a file path in the argument list to include arguments from a file.',
        )

    def convert_arg_line_to_args(self, line):
        return shlex.split(line)

class SetObligatePoly(argparse.Action):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default = argparse.SUPPRESS  # Don't assign anything--we're effectively a special "store_true"
        self.nargs = 0

    def __call__(self, parser, ns, values, opt):
        ns.voices = 1
        ns.obpoly = True

class SetVoice(argparse.Action):
    def __call__(self, parser, ns, values, opt):
        ns.voicen = values

class SetVoiceAll(argparse.Action):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nargs = 0

    def __call__(self, parser, ns, values, opt):
        ns.voicen = None

class SetVoiceOpt(argparse.Action):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default = argparse.SUPPRESS  # We have custom init logic

    def ensure_existence(self, ns):
        if not hasattr(ns, '_voices'):
            ns._voices = ns.voices
        if ns.voices != ns._voices:
            raise ValueError(f'Cannot set voices (to {ns.voices}, was {ns._voices}) after configuring a voice option')
        if not hasattr(ns, self.dest):
            setattr(ns, self.dest, self.produce_default_seq(ns))

    def produce_default_seq(self, ns):
        return [self.const] * ns.voices

    def __call__(self, parser, ns, values, opt):
        self.ensure_existence(ns)
        for i in (range(ns._voices) if ns.voicen is None else ns.voicen):
            if i >= ns._voices:
                raise ValueError(f'Cannot set property {self.dest!r} on voice {i} as there are only {ns._voices} voices')
            self.call_on_voice(i, ns, values)

    def call_on_voice(self, voice, ns, values):
        getattr(ns, self.dest)[voice] = values

class Copy(object):
    def __init__(self, name):
        self.name = name

class Expr(object):
    def __init__(self, expr):
        self.expr = compile(expr, 'param', 'eval')

class AddVoiceOpt(SetVoiceOpt):
    @staticmethod
    def interp_rand(s):
        a, _, b = s.partition(',')
        a, b = float(a), float(b)
        return a + random.random() * (b - a)

    @staticmethod
    def interp_randint(s):
        a, _, b = s.partition(',')
        a, b = int(a), int(b)
        return random.randint(a, b)

    TYPE_FUNCS = {
            's': lambda x: x,
            'str': lambda x: x,
            'i': int,
            'int': int,
            'f': float,
            'float': float,
            'r': interp_rand,
            'rand': interp_rand,
            'ri': interp_randint,
            'randint': interp_randint,
            'c': Copy,
            'copy': Copy,
            'e': Expr,
            'expr': Expr,
    }

    def produce_default_seq(self, ns):
        return [{} for _ in range(ns.voices)]

    def call_on_voice(self, voice, ns, values):
        k, v = values.split('=')
        k, sep, t = k.partition(':')
        if t:
            v = self.TYPE_FUNCS[t](v)
        getattr(ns, self.dest)[voice][k] = v

class RemoveVoiceOpt(AddVoiceOpt):
    def call_on_voice(self, voice, ns, values):
        del getattr(ns, self.dest)[voice][values]

TYPE=b'SUPC'

parser = CustomArgumentParser()
parser.add_argument('-p', '--port', type=int, default=13676, help='Sets the port to listen on')
parser.add_argument('-B', '--bind', default='', help='Bind to this address')
parser.add_argument('-S', '--server', default='127.0.0.1', help='Send OSC to SCSynth at this address')
parser.add_argument('-P', '--server-port', type=int, default=57110, help='Send OSC to SCSynth on this port')
parser.add_argument('--server-bind', default='127.0.0.1', help='Address to bind the OSC socket to')
parser.add_argument('--server-bind-port', type=int, default=0, help='Port to bind the OSC socket to')
parser.add_argument('-u', '--uid', default='', help='Set the UID (identifer) of this client for routing')
#parser.add_argument('--exclusive', action='store_true', help="Don't query the server for a new node ID--assume they're incremental. Boosts performance, but only sound if we're the only client.")
parser.add_argument('--start-id', type=int, default=2, help='Starting node ID to allocate (further IDs are allocated sequentially)')
parser.add_argument('-G', '--group', type=int, default=1, help='SC Group to add to (should exist before starting)')
parser.add_argument('--attach', type=int, default=1, help='SC Target attachment method (head=0, tail, before, after, replace=4)')
parser.add_argument('--stop-with-free', action='store_true', help='Kill a node with n_free rather than setting its gate to 0')
parser.add_argument('--slack', type=float, default=0.002, help='Add this much to duration to allow late SAMEPHASE to work')

group = parser.add_mutually_exclusive_group()
group.add_argument('-n', '--voices', type=int, default=1, help='Number of voices to advertise (does not affect synth polyphony)')
group.add_argument('-N', '--obligate-polyphone', help='Set this instance as an Obligate Polyphone (arbitrary voice count)--incompatible with -n/--voices, and there is effectively only one voice to configure', action=SetObligatePoly)
parser.set_defaults(obpoly = False)

group = parser.add_argument_group('Voice Selection', 'Options which select a voice to configure. Specify AFTER setting the number of voices!')
group.add_argument('-v', '--voice', type=int, nargs='+', help='Following Voice Options apply to these voices', action=SetVoice)
group.add_argument('-V', '--all-voices', help='Following Voice Options apply to all voices', action=SetVoiceAll)
parser.set_defaults(voicen = None)

group = parser.add_argument_group('Voice Options', 'Options which configure one or more voices.')
group.add_argument('-s', '--synth', const='default', help='Set the SC synth name for these voices', action=SetVoiceOpt)
group.add_argument('-A', '--amplitude', type=float, const=1.0, help='Set a custom amplitude for these voices', action=SetVoiceOpt)
group.add_argument('-T', '--transpose', type=float, const=1.0, help='Set a frequency multiplier(!) for these voices', action=SetVoiceOpt)
group.add_argument('-R', '--random', type=float, const=0.0, help='Uniformly vary (in frequency space!) by up to +/- this value (as a fraction of the sent frequency)', action=SetVoiceOpt)
group.add_argument('--param', help='Set an arbitrary parameter for the voice synth (see --help-oparam)', action=AddVoiceOpt)
group.add_argument('--unset-param', dest='param', help='Unset an arbitrary parameter', action=RemoveVoiceOpt)
group.add_argument('--help-param', action='store_true', help='Display the documentation for the --param option')

help_param = '''
Use --param <name>[:<type>]=<value> to send arbitrary parameters to the synth
at play time--this includes whenever the ITL Chorus sends SAMEPHASE plays
(usually as part of a pitchbend expression). The values in angle brackets (<>)
are to be replaced, including the brackets themselves; the section in square
brackets ([]) is optional, defaulting to :str, and the brackets must not be
included.

The entire second word (according to your shell) is consumed. Remember to use
your shell's quoting facilities if, e.g., you need to include spaces or special
characters.

The name is sent as a symbol verbatim to SC; the value is interpreted based on
the type given:

- s, str: The default; the value is sent as a string.
- i, int: The value is interpreted as as decimal integer.
- f, float: The value is interpreted as a Python-syntax float.
- r, rand: The value is of the form "<a>,<b>" where a and b are Python-syntax
  floats. On each play, the value is chosen uniformly randomly from this range.
- ri, randint: The value is of the form "<a>,<b>" where a and b are decimal
  integers. On each play, the value is an integer chosen uniformly randomly
  from this range, inclusive.
- c, copy: The value is copied from another parameter named. This is useful for
  making a value follow other named parameters provided by the implementation,
  such as freq or amp. Note that copy values are interpreted only after the
  other parameters are assigned, but the ordering within all copy params is
  undefined, so they should not depend on each other.
- e, expr: The value is interpreted as a Python expression and evaluated, the
  type of the result being used verbatim. This is done after all copies are
  resolved, but the order of evaluation of expr values among themselves is
  undefined, so they should not depend on each other. The expression has access
  to the global scope, and its local scope consists of the parameters presently
  defined--so they can be named as regular python identifiers.
'''

def make_play_pkt(args, synth, nid, **ctrls):
    msg = OscMessageBuilder('/s_new')
    msg.add_arg(synth)
    msg.add_arg(nid)
    msg.add_arg(args.attach)
    msg.add_arg(args.group)
    print(ctrls)
    for name, value in ctrls.items():
        msg.add_arg(name)
        msg.add_arg(value)
    return msg.build().dgram

def make_set_pkt(nid, **ctrls):
    msg = OscMessageBuilder('/n_set')
    msg.add_arg(nid)
    for name, value in ctrls.items():
        msg.add_arg(name)
        msg.add_arg(value)
    return msg.build().dgram

def make_stop_pkt(nid):
    msg = OscMessageBuilder('/n_free')
    msg.add_arg(nid)
    return msg.build().dgram

def make_version_pkt():
    msg = OscMessageBuilder('/version')
    return msg.build().dgram

def _get_second(pair):
    return pair[1]

def _not_none(pair):
    return pair[1] is not None

def free_voice(args, idx, osc, srv, nodes, deadlines, lk):
    with lk:
        if nodes[idx] is None:
            return
        if args.stop_with_free:
            osc.sendto(make_stop_pkt(ndes[idx]), srv)
        else:
            osc.sendto(make_set_pkt(nodes[idx], gate=0.0), srv)
        nodes[idx] = None
        deadlines[idx] = None

def check_deadlines(args, osc, srv, nodes, deadlines, lk):
    while True:
        with lk:
            dls = list(filter(_not_none, enumerate(deadlines)))
        if not dls:
            time.sleep(0.05)
            continue
        idx, cur = min(dls, key=_get_second)
        now = time.time()
        if cur > now:
            time.sleep(max(0.0001, cur - time.time()))  # account for time since recording now
        else:
            free_voice(args, idx, osc, srv, nodes, deadlines, lk)

def main():
    args = parser.parse_args()
    for act in parser._actions:
        if isinstance(act, SetVoiceOpt):
            act.ensure_existence(args)
    args.uid = args.uid.encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))

    osc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    osc.bind((args.server_bind, args.server_bind_port))

    osc_srv = (args.server, args.server_port)

    osc.sendto(make_version_pkt(), osc_srv)
    osc.settimeout(5)
    data, _ = osc.recvfrom(4096)
    msg = OscMessage(data)
    assert msg.address == "/version.reply"
    prog, major, minor, patch, branch, commit = list(msg)
    print(f'Connected to {prog} {major}.{minor}.{patch}, branch {branch}, commit {commit}')

    def ignore_input():
        osc.settimeout(None)
        while True:
            osc.recv(4096)

    ignore_thread = threading.Thread(target=ignore_input)
    ignore_thread.daemon = True
    ignore_thread.start()

    nodes = [None] * args.voices
    dls = [None] * args.voices
    lock = threading.RLock()

    dl_thread = threading.Thread(target=check_deadlines, args=(args, osc, osc_srv, nodes, dls, lock))
    dl_thread.daemon = True
    dl_thread.start()

    while True:
        data = b''
        while not data:
            try:
                data, cli = sock.recvfrom(4096)
            except socket.error:
                pass

        pkt = Packet.FromStr(data)
        print(f'{bytes(pkt)!r}')
        if pkt.cmd == CMD.KA:
            pass
        elif pkt.cmd == CMD.PING:
            sock.sendto(data, cli)
        elif pkt.cmd == CMD.QUIT:
            break
        elif pkt.cmd == CMD.PLAY:
            voice = pkt.data[4]
            dur = pkt.data[0] + pkt.data[1] / 1000000.0
            freq = pkt.data[2] * args.transpose[voice]
            if args.random[voice] != 0.0:
                freq *= 1.0 + args.random[voice] * (random.random() + 1) / 2
            amp = pkt.as_float(3) * args.amplitude[voice]
            flags = pkt.data[5]
            synth = args.synth[voice]
            nid = args.start_id
            args.start_id += 1
            params = dict(args.param[voice], freq=freq, amp=amp, dur=dur)
            for k in [p[0] for p in params.items() if isinstance(p[1], Copy)]:
                params[k] = params[params[k].name]
            for k in [p[0] for p in params.items() if isinstance(p[1], Expr)]:
                params[k] = eval(params[k].expr, None, params)
            
            if freq == 0:  # STOP
                free_voice(args, voice, osc, osc_srv, nodes, dls, lock)
            elif flags & PLF.SAMEPHASE and nodes[voice] is not None:
                with lock:
                    osc.sendto(
                            make_set_pkt(nodes[voice], **params),
                            osc_srv,
                    )
                    dls[voice] = time.time() + dur + args.slack
            else:
                with lock:
                    if nodes[voice] is not None:
                        free_voice(args, voice, osc, osc_srv, nodes, dls, lock)
                    nodes[voice] = nid
                    dls[voice] = time.time() + dur + args.slack
                    osc.sendto(
                            make_play_pkt(args, synth, nid, **params),
                            osc_srv,
                    )
        elif pkt.cmd == CMD.CAPS:
            data = [0] * 8
            data[0] = OBLIGATE_POLYPHONE if args.obpoly else args.voices
            data[1] = stoi(TYPE)
            for i in range(len(args.uid)//4 + 1):
                data[i+2] = stoi(args.uid[4*i:4*(i+1)])
            sock.sendto(bytes(Packet(CMD.CAPS, *data)), cli)
        else:
            pass  # unrec

if __name__ == '__main__':
    main()
