'''
itl_chorus -- ITL Chorus Suite
ivtomid -- Convert IV to MIDI

Revert the conversion of mkiv.
'''

import xml.etree.ElementTree as ET
import optparse, sys
import midi

parser = optparse.OptionParser()
parser.add_option('
