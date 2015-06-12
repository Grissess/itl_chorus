'''
itl_chorus -- ITL Chorus Suite
mkiv -- Make Intervals

This simple script (using python-midi) reads a MIDI file and makes an interval
(.iv) file (actually XML) that contains non-overlapping notes.

TODO:
-Reserve channels by track
-Reserve channels by MIDI channel
-Pitch limits for channels
-MIDI Control events
'''

import xml.etree.ElementTree as ET
import midi
import sys
import os

pat = midi.read_midifile(sys.argv[1])
iv = ET.Element('iv')
iv.set('version', '1')
iv.set('src', os.path.basename(sys.argv[1]))

##### Merge events from all tracks into one master list, annotated with track and absolute times #####
print 'Merging events...'

class MergeEvent(object):
	__slots__ = ['ev', 'tidx', 'abstime']
	def __init__(self, ev, tidx, abstime):
		self.ev = ev
		self.tidx = tidx
		self.abstime = abstime
	def __repr__(self):
		return '<ME %r in %d @%f>'%(self.ev, self.tidx, self.abstime)

events = []
bpm_at = {0: 120}

for tidx, track in enumerate(pat):
	abstime = 0
	absticks = 0
	for ev in track:
		if isinstance(ev, midi.SetTempoEvent):
			absticks += ev.tick
			bpm_at[absticks] = ev.bpm
		else:
			if isinstance(ev, midi.NoteOnEvent) and ev.velocity == 0:
				ev.__class__ = midi.NoteOffEvent #XXX Oww
			bpm = filter(lambda pair: pair[0] <= absticks, bpm_at.items())[-1][1]
			abstime += (60.0 * ev.tick) / (bpm * pat.resolution)
			absticks += ev.tick
			events.append(MergeEvent(ev, tidx, abstime))

print 'Sorting events...'

events.sort(key = lambda ev: ev.abstime)

##### Use merged events to construct a set of streams with non-overlapping durations #####
print 'Generating streams...'

class DurationEvent(MergeEvent):
	__slots__ = ['duration']
	def __init__(self, me, dur):
		MergeEvent.__init__(self, me.ev, me.tidx, me.abstime)
		self.duration = dur

class NoteStream(object):
	__slots__ = ['history', 'active']
	def __init__(self):
		self.history = []
		self.active = None
	def IsActive(self):
		return self.active is not None
	def Activate(self, mev):
		self.active = mev
	def Deactivate(self, mev):
		self.history.append(DurationEvent(self.active, mev.abstime - self.active.abstime))
		self.active = None
	def WouldDeactivate(self, mev):
		if not self.IsActive():
			return False
		return mev.ev.pitch == self.active.ev.pitch and mev.tidx == self.active.tidx

notestreams = []
auxstream = []

for mev in events:
	if isinstance(mev.ev, midi.NoteOnEvent):
		for stream in notestreams:
			if not stream.IsActive():
				stream.Activate(mev)
				break
		else:
			stream = NoteStream()
			notestreams.append(stream)
			stream.Activate(mev)
	elif isinstance(mev.ev, midi.NoteOffEvent):
		for stream in notestreams:
			if stream.WouldDeactivate(mev):
				stream.Deactivate(mev)
				break
		else:
			print 'WARNING: Did not match %r with any stream deactivation.'%(mev,)
	else:
		auxstream.append(mev)

lastabstime = events[-1].abstime

for ns in notestreams:
	if not ns:
		print 'WARNING: Active notes at end of playback.'
		ns.Deactivate(MergeEvent(ns.active, ns.active.tidx, lastabstime))

print 'Generated %d streams'%(len(notestreams),)

##### Write to XML and exit #####

ivmeta = ET.SubElement(iv, 'meta')
ivbpms = ET.SubElement(ivmeta, 'bpms')
abstime = 0
prevticks = 0
prev_bpm = 120
for absticks, bpm in sorted(bpm_at.items(), key = lambda pair: pair[0]):
	abstime += ((absticks - prevticks) * 60.0) / (prev_bpm * pat.resolution)
	prevticks = absticks
	ivbpm = ET.SubElement(ivbpms, 'bpm')
	ivbpm.set('bpm', str(bpm))
	ivbpm.set('ticks', str(absticks))
	ivbpm.set('time', str(abstime))

ivstreams = ET.SubElement(iv, 'streams')

for ns in notestreams:
	ivns = ET.SubElement(ivstreams, 'stream')
	ivns.set('type', 'ns')
	for note in ns.history:
		ivnote = ET.SubElement(ivns, 'note')
		ivnote.set('pitch', str(note.ev.pitch))
		ivnote.set('vel', str(note.ev.velocity))
		ivnote.set('time', str(note.abstime))
		ivnote.set('dur', str(note.duration))

ivaux = ET.SubElement(ivstreams, 'stream')
ivaux.set('type', 'aux')

fw = midi.FileWriter()
fw.RunningStatus = None # XXX Hack

for mev in auxstream:
	ivev = ET.SubElement(ivaux, 'ev')
	ivev.set('time', str(mev.abstime))
	ivev.set('data', repr(fw.encode_midi_event(mev.ev)))

print 'Done.'
open(os.path.splitext(os.path.basename(sys.argv[1]))[0]+'.iv', 'w').write(ET.tostring(iv))
