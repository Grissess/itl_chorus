# What this is

The ITL Chorus is a very simple, loosely bundled package for playing MIDI in
real time over a network. Presently, it consists of three different frontends:

- `mkiv.py`: Makes an *i*nter*v*al (`.iv`) file from a MIDI (usually `.mid`)
  file. The interval file is an XML document (easily compressed) consisting of
  the necessary information required to play back *voices* or *streams* such
  that no notes overlap (and duration information is available).
- `client.c`: A bare-minimum C program designed to run on even the most spartan
  Linux systems; it basically implements `beep` over UDP.
- `client.py`: A far-more-functional Python program with advanced options,
  using the pyaudio API.
- `broadcast.py`: Accepts an interval file, assigns clients to streams, and
  plays a piece in real time.

In general, you would use the tooling in precisely this order; generate an
interval file with `mkiv.py` from a good MIDI performance (of your own acquiry
:), either compile and run `./client` *as root* or run python client.py on all
the machines on a LAN that you would like to beep along, and then run
`broadcast.py` with the generated interval file on any machine also on that LAN
(potentially also one of the clients).

# Troubleshooting

In my experience, the most annoying errors come about as the following:

- No PC speaker. Many modern computers/motherboards omit this ancient piece of
  IBM technology entirely. Presumably, emulation is available (especially in
  desktop environments), but this normally requires a kernel-mode driver (as it
  has to respond to the very low-level syscall that actually would beep the
  speaker). ALSA purportedly provides snd_pcsp, but I've not seen it work yet.
  It should be noted that the python client.py script uses *regular* PCM
  speakers to operate, and so can work under these conditions.
- Network issues. `client` doesn't really check for any LAN, happily listening
  on whatever interfaces it can find at the time. Many very basic installations
  of Linux seem to not `dhclient` properly, even if the link is up, so you will
  want to make sure that your ip information is set up how you like it *before*
  running `client`.
- Lack of a compiler. Again, some bare-bones distributions don't ship with a
  compiler by default (I don't even know how you can use Linux like that :).
  Many nonetheless have package managers that will get a compiler and build
  environment for you. (On Debian and derivatives, `build-essential` works.)

Please submit an issue if something else seems off!

# Options

All the scripts here (except the C program) have a plethora of options, most
of which are documented both at the beginning of the source and if you simply
pass `--help` or `-h` to them. Feel free to experiment!

# Hacking

The .iv file format that is used extensively in communicating information is
certainly not any standard that I am aware of, but it seems like a rather
convenient standard for simple authorship. While I have no plans to write an
IV editor at the moment, that may change; in the meantime, whosoever would like
to do so should know the following about the IV files:

- They are in XML--go ahead and open them in your favorite XML browser!
- Their root element is "iv" with no decided namespace yet.
- Under the root, there is a "meta" element with metainformation about the
  compilation process--at present, this includes things like the "bpms" element
  which has a "bpm" for each time period parsed out of the original MIDI.
- Also under the root, and arguably most importantly, is the "streams" element
  that possesses all the "stream" elements that correspond to playable voices.
- Each stream has a "type" attribute which determines what it is ("ns" is a note
  stream--the ones that have playable notes, and "aux" is a stream of non-note
  MIDI events), and an optional "group" attribute which determines what group
  it belongs to (`broadcast.py` uses this for routing).
- All note streams (type="ns") *should* contain non-overlapping notes, in the
  sense that any "note" element in there should have a `time + dur` not greater
  than its next note. Additionally, all notes in such a stream *should* be
  sorted by time. Breaking either of these standards is not an egregious violation,
  and may prove to be interesting, but (at the moment) it will prevent `broadcast.py`
  from working properly. In addition, it should be noted that the clients are
  *designed* to overwrite one incoming note with the next, regardless of whether or
  not this interrupts the duration of the previous one--this is how "live mode" and "silence" work.

# Todo

- Polyphony--have multiple voices on one machine
  - Mixed polyphony: the audio is the result of mixing (saturating addition, etc.)--only doable with PCM
  - LFO polyphony: tones are "rapidly" switched between (how old microcomputers used to accomplish this with one beep speaker)
- Preloading--send events to clients early to avoid jitter problems with the network
  - Would require a network time synchronization to work effectively; makes the broadcaster have less control over nuanced timing
- Other stream types--e.g., PCM streams for raw audio data
  - More clientside implementation work
  - Definitely a higher bandwidth--might interfere with critical timing, and would almost certainly need preloading
- Percussion--implement percussive instruments
  - Requires an analysis of how current DAWs and MIDI editors mark "percussion" tracks--with a program change? GM specifies channel 10...
- Soundfonts--have the ability to significantly affect the instrumentation of the clients
  - Would also be nice to do this from the broadcaster's end without introducing RCE
  - Might require integration of another large libary like fluidsynth--at which point this would just be "networked MIDI" :)
- Code cleanup--make the entire project slightly more modular and palatable
