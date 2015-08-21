#IV to arduino array computer

import xml.etree.ElementTree as ET
import sys

iv = ET.parse(sys.argv[1]).getroot()

streams = iv.findall('./streams/stream[@type="ns"]')
if len(streams) > 3:
    print 'WARNING: Too many streams'

for i in xrange(min(3, len(streams))):
    stream = streams[i]
    notes = stream.findall('note')

# First, the header
    sys.stdout.write('const uint16_t track%d[] PROGMEM = {\n'%(i,))

# For the first note, write out the delay needed to get there
    if notes[0].get('time') > 0:
        sys.stdout.write('%d, 0,\n'%(int(float(notes[0].get('time'))*1000),))

    for idx, note in enumerate(notes):
        sys.stdout.write('%d, FREQ(%d),\n'%(int(float(note.get('dur'))*1000), int(440.0 * 2**((int(note.get('pitch'))-69)/12.0))))
        if idx < len(notes)-1 and float(note.get('time'))+float(note.get('dur')) < float(notes[idx+1].get('time')):
            sys.stdout.write('%d, 0,\n'%(int(1000*(float(notes[idx+1].get('time')) - (float(note.get('time')) + float(note.get('dur'))))),))

# Finish up the stream
    sys.stdout.write('};\n\n')
