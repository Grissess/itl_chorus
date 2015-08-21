# IV file viewer

import xml.etree.ElementTree as ET
import optparse
import sys

parser = optparse.OptionParser()
parser.add_option('-n', '--number', dest='number', action='store_true', help='Show number of tracks')
parser.add_option('-g', '--groups', dest='groups', action='store_true', help='Show group names')
parser.add_option('-N', '--notes', dest='notes', action='store_true', help='Show number of notes')
parser.add_option('-m', '--meta', dest='meta', action='store_true', help='Show meta track information')
parser.add_option('-h', '--histogram', dest='histogram', action='store_true', help='Show a histogram distribution of pitches')
parser.add_option('-H', '--histogram-tracks', dest='histogram_tracks', action='store_true', help='Show a histogram distribution of pitches per track')
parser.add_option('-d', '--duration', dest='duration', action='store_true', help='Show the duration of the piece')
parser.add_option('-D', '--duty-cycle', dest='duty_cycle', action='store_true', help='Show the duration of the notes within tracks, and as a percentage of the piece duration')

parser.add_option('-a', '--almost-all', dest='almost_all', action='store_true', help='Show useful information')
parser.add_option('-A', '--all', dest='all', action='store_true', help='Show everything')

options, args = parser.parse_args()

if options.almost_all or options.all:
    options.number = True
    options.groups = True
    options.notes = True
    options.histogram = True
    options.duration = True
    if options.all:
        options.meta = True
        options.histogram_tracks= True
        options.duty_cycle = True

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

