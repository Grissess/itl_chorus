'''
voice -- Voices

A voice is a simple, singular unit of sound generation that encompasses the following
properties:
-A *generator*: some function that generates a waveform. As an input, it receives theta,
 the phase of the signal it is to generate (in [0, 2pi)) and, as an output, it produces
 the sample at that point, a normalized amplitude value in [-1, 1].
-An *envelope*: a function that receives a boolean (the status of whether or not a note
 is playing now) and the change in time, and outputs a factor in [0, 1] that represents
 a modification to the volume of the generator (pre-output mix).
All of these functions may internally store state or other data, usually by being 
implemented as a class with a __call__ method.

Voices are meant to generate audio data. This can be done in a number of ways, least to
most abstracted:
-A sample at a certain phase (theta) may be gotten from the generator; this can be done
 by calling the voice outright;
-A set of samples can be generated via the .samples() method, which receives the number
 of samples to generate and the phase velocity (a function of the sample rate and the
 desired frequency of the waveform's period; this can be calculated using the static
 method .phase_vel());
-Audio data with enveloping can be generated using the .data() method, which calls the
 envelope function as if the note is depressed at the given phase velocity; if the
 freq is specified as None, then the note is treated as released. Note that
 this will often be necessary for envelopes, as many of them are stateful (as they
 depend on the first derivative of time). Also, at this level, the Voice will maintain
 some state (namely, the phase at the end of generation) which will ensure (C0) smooth
 transitions between already smooth generator functions, even if the frequency changes.
-Finally, a pyaudio-compatible stream callback can be provided with .pyaudio_scb(), a
 method that returns a function that arranges to call .data() with the appropriate values.
 The freq input to .data() will be taken from the .freq member of the voice in a possibly
 non-atomic manner.
'''

import math
import pyaudio
import struct

def norm_theta(theta):
    return theta % (2*math.pi)

def norm_amp(amp):
    return min(1.0, max(-1.0, amp))

def theta2lin(theta):
    return theta / (2*math.pi)

def lin2theta(lin):
    return lin * 2*math.pi

class ParamInfo(object):
    PT_ANY =       0x0000
    PT_CONST =     0x0001
    PT_SPECIAL =   0x0002
    PT_INT =       0x0100
    PT_FLOAT =     0x0200
    PT_STR =       0x0400
    PT_THETA =     0x0102
    PT_TIME_SEC =  0x0202
    PT_SAMPLES =   0x0302
    PT_REALTIME =  0x0402
    def __init__(self, name, tp=PT_ANY):
        self.name = name
        self.tp = tp

class GenInfo(object):
    def __init__(self, name, *params):
        self.name = name
        self.params = list(params)

class Generator(object):
    class __metaclass__(type):
        def __init__(self

class Voice(object):
    @classmethod
    def register_gen(cls, name, params):
    def __init__(self, generator=None, envelope=None):
        self.generator = generator or self.DEFAULT_GENERATOR
        self.envelope = envelope or self.DEFAULT_ENVELOPE
        self.phase = 0
        self.freq = None
    def __call__(self, theta):
        return norm_amp(self.generator(norm_theta(theta)))
    @staticmethod
    def phase_vel(freq, samp_rate):
        return 2 * math.pi * freq / samp_rate
    def samples(self, frames, pvel):
        for i in xrange(frames):
            yield self(self.phase)
            self.phase = norm_theta(self.phase + pvel)
    def data(self, frames, freq, samp_rate):
        period = 1.0/samp_rate
        status = freq is not None
        for samp in self.samples(frames, self.phase_vel(freq, samp_rate)):
            yield samp * self.envelope(status, period)
    def pyaudio_scb(self, rate, fmt=pyaudio.paInt16):
        samp_size = pyaudio.get_sample_size(fmt)
        maxint = (1 << (8*samp_size)) - 1
        dtype = ['!', 'h', 'i', '!', 'l', '!', '!', '!', 'q'][samp_size]
        def __callback(data, frames, time, status, self=self, rate=rate, maxint=maxint, dtype=dtype):
            return struct.pack(dtype*frames, *[maxint*int(i) for i in self.data(frames, self.freq, rate)])
        return __callback

class VMeanMixer(Voice):
    def __init__(self, *voices):
        self.voices = list(voices)
    def __call__(self, theta):
        return sum([i(theta)/len(self.voices) for i in self.voices])

class VSumMixer(Voice):
    def __init__(self, *voices):
        self.voices = list(voices)
    def __call__(self, theta):
        return sum([i(theta) for i in self.voices])
