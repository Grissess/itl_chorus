# A visualizer for the Python client (or any other client) rendering to a mapped file

import optparse
import mmap
import os
import time
import struct
import colorsys
import math

import pygame
import pygame.gfxdraw

parser = optparse.OptionParser()
parser.add_option('--map-file', dest='map_file', default='client_map', help='File mapped by -G mapped')
parser.add_option('--map-samples', dest='map_samples', type='int', default=4096, help='Number of samples in the map file (MUST agree with client)')
parser.add_option('--pg-samp-width', dest='samp_width', type='int', help='Set the width of the sample pane (by default display width / 2)')
parser.add_option('--pg-fullscreen', dest='fullscreen', action='store_true', help='Use a full-screen video mode')
parser.add_option('--pg-no-colback', dest='no_colback', action='store_true', help='Don\'t render a colored background')
parser.add_option('--pg-low-freq', dest='low_freq', type='int', default=40, help='Low frequency for colored background')
parser.add_option('--pg-high-freq', dest='high_freq', type='int', default=1500, help='High frequency for colored background')
parser.add_option('--pg-log-base', dest='log_base', type='int', default=2, help='Logarithmic base for coloring (0 to make linear)')

options, args = parser.parse_args()

while not os.path.exists(options.map_file):
    print 'Waiting for file to exist...'
    time.sleep(1)

f = open(options.map_file)
mapping = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
f.close()

fixfmt = '>f'
fixfmtsz = struct.calcsize(fixfmt)
sigfmt = '>' + 'f' * options.map_samples
sigfmtsz = struct.calcsize(sigfmt)
strfmtsz = len(mapping) - fixfmtsz - sigfmtsz
print 'Map size:', len(mapping), 'Appendix size:', strfmtsz
print 'Size triple:', fixfmtsz, sigfmtsz, strfmtsz
STREAMS = strfmtsz / struct.calcsize('>Lf')
strfmt = '>' + 'Lf' * STREAMS
print 'Detected', STREAMS, 'streams'

pygame.init()

WIDTH, HEIGHT = 640, 480
dispinfo = pygame.display.Info()
if dispinfo.current_h > 0 and dispinfo.current_w > 0:
    WIDTH, HEIGHT = dispinfo.current_w, dispinfo.current_h

flags = 0
if options.fullscreen:
    flags |= pygame.FULLSCREEN

disp = pygame.display.set_mode((WIDTH, HEIGHT), flags)
WIDTH, HEIGHT = disp.get_size()
SAMP_WIDTH = WIDTH / 2
if options.samp_width:
    SAMP_WIDTH = options.samp_width
BGR_WIDTH = WIDTH - SAMP_WIDTH
HALFH = HEIGHT / 2
PFAC = HEIGHT / 128.0
sampwin = pygame.Surface((SAMP_WIDTH, HEIGHT))
sampwin.set_colorkey((0, 0, 0))
lastsy = HALFH
bgrwin = pygame.Surface((BGR_WIDTH, HEIGHT))
bgrwin.set_colorkey((0, 0, 0))

clock = pygame.time.Clock()
font = pygame.font.SysFont(pygame.font.get_default_font(), 24)

def rgb_for_freq_amp(f, a):
    a = max((min((a, 1.0)), 0.0))
    pitchval = float(f - options.low_freq) / (options.high_freq - options.low_freq)
    if options.log_base == 0:
        try:
            pitchval = math.log(pitchval) / math.log(options.log_base)
        except ValueError:
            pass
    bgcol = colorsys.hls_to_rgb(min((1.0, max((0.0, pitchval)))), 0.5 * (a ** 2), 1.0)
    return [int(i*255) for i in bgcol]

while True:
    DISP_FACTOR = struct.unpack(fixfmt, mapping[:fixfmtsz])[0]
    LAST_SAMPLES = struct.unpack(sigfmt, mapping[fixfmtsz:fixfmtsz+sigfmtsz])
    VALUES = struct.unpack(strfmt, mapping[fixfmtsz+sigfmtsz:])
    FREQS, AMPS = VALUES[::2], VALUES[1::2]
    if options.no_colback:
        disp.fill((0, 0, 0), (0, 0, WIDTH, HEIGHT))
    else:
        gap = WIDTH / STREAMS
        for i in xrange(STREAMS):
            FREQ = FREQS[i]
            AMP = AMPS[i]
            if FREQ > 0:
                bgcol = rgb_for_freq_amp(FREQ, AMP)
            else:
                bgcol = (0, 0, 0)
            disp.fill(bgcol, (i*gap, 0, gap, HEIGHT))

    bgrwin.scroll(-1, 0)
    bgrwin.fill((0, 0, 0), (BGR_WIDTH - 1, 0, 1, HEIGHT))
    for i in xrange(STREAMS):
        FREQ = FREQS[i]
        AMP = AMPS[i]
        if FREQ > 0:
            try:
                pitch = 12 * math.log(FREQ / 440.0, 2) + 69
            except ValueError:
                pitch = 0
        else:
            pitch = 0
        col = [min(max(int(AMP * 255), 0), 255)] * 3
        bgrwin.fill(col, (BGR_WIDTH - 1, HEIGHT - pitch * PFAC - PFAC, 1, PFAC))

    sampwin.fill((0, 0, 0), (0, 0, SAMP_WIDTH, HEIGHT))
    x = 0
    for i in LAST_SAMPLES:
        sy = int(i * HALFH + HALFH)
        pygame.gfxdraw.line(sampwin, x - 1, lastsy, x, sy, (0, 255, 0))
        x += 1
        lastsy = sy

    disp.blit(bgrwin, (0, 0))
    disp.blit(sampwin, (BGR_WIDTH, 0))

    if DISP_FACTOR != 0:
        tsurf = font.render('%+011.6g'%(DISP_FACTOR,), True, (255, 255, 255), (0, 0, 0))
        disp.fill((0, 0, 0), tsurf.get_rect())
        disp.blit(tsurf, (0, 0))

    pygame.display.flip()

    for ev in pygame.event.get():
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                pygame.quit()
                exit()
        elif ev.type == pygame.QUIT:
            pygame.quit()
            exit()

    if not os.path.exists(options.map_file):
        pygame.quit()
        exit()

    clock.tick(60)
