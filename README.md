# What this is

The ITL Chorus is a very simple, loosely bundled package for playing MIDI in real time over a network. Presently, it consists of three different frontends:

- `mkiv.py`: Makes an *i*nter*v*al (`.iv`) file from a MIDI (usually `.mid`) file. The interval file is an XML document (easily compressed) consisting of the necessary information required to play back *voices* or *streams* such that no notes overlap (and duration information is available).
- `client.c`: A bare-minimum C program designed to run on even the most spartan Linux systems; it basically implements `beep` over UDP.
- `broadcast.py`: Accepts an interval file, assigns clients to streams, and plays a piece in real time.

In general, you would use the tooling in precisely this order; generate an interval file with `mkiv.py` from a good MIDI performance (of your own acquiry :), compile and run `./client` *as root* on all the machines on a LAN that you would like to beep along, and then run `broadcast.py` with the generated interval file on any machine also on that LAN (potentially also one of the clients).

# Troubleshooting

In my experience, the most annoying errors come about as the following:

- No PC speaker. Many modern computers/motherboards omit this ancient piece of IBM technology entirely. Presumably, emulation is available (especially in desktop environments), but this normally requires a kernel-mode driver (as it has to respond to the very low-level syscall that actually would beep the speaker). ALSA purportedly provides snd_pcsp, but I've not seen it work yet.
- Network issues. `client` doesn't really check for any LAN, happily listening on whatever interfaces it can find at the time. Many very basic installations of Linux seem to not `dhclient` properly, even if the link is up, so you will want to make sure that your ip information is set up how you like it *before* running `client`.
- Lack of a compiler. Again, some bare-bones distributions don't ship with a compiler by default (I don't even know how you can use Linux like that :). Many nonetheless have package managers that will get a compiler and build environment for you. (On Debian and derivatives, `build-essential` works.)

Please submit an issue if something else seems off!

# Obscure features

Not particularly well documented, `broadcast` supports some silly command-line magic:

- Using `-q` as a filename sends QUIT to all reachable clients, causing them to exit.
- Using `-t` as a filename sends test tones (440 for 0.25s, 880 for 0.25s) to all clients. The latter tone overlaps with the former tone, so you should hear N+1 tones (with N-1 octave chords) play across all clients in a somewhat non-deterministic order. From this, it should be easy to infer if a client is not network-reachable, or has a bad speaker.
- When playing a file, if a floating-point value is specified as the second argument, this represents a time remapping. If the original MIDI was consistently too slow or too fast, you can use values less than or greater than 1, respectively, to control how real time is mapped to stream time.

Note that `-q` and `-t` "as a filename" really means "as a filename"; `broadcast` will usually report a "Bad file" error afterward as it tries to open files named `-q` and `-t` after doing the relevant special command. (Alternatively, if they do exist and are valid interval files, it will play them :)
