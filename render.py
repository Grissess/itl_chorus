# A visualizer for the Python client (or any other client) rendering to a mapped file

import optparse
import mmap
import os
import time
import struct
import colorsys
import math

parser = optparse.OptionParser()
parser.add_option('-E', '--engine', dest='engine', default='pygame', help='Rendering engine to use')
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

if options.engine == 'pygame':
    import pygame
    import pygame.gfxdraw

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

elif options.engine == 'glfw':
    import array, ctypes
    import glfw
    from OpenGL import GL
    from OpenGL.GL import *

    if not glfw.init():
        print 'GLFW: Init failed'
        exit()

    monitor = glfw.get_primary_monitor()
    mode = glfw.get_video_mode(monitor)

    glfw.window_hint(glfw.RED_BITS, mode.bits.red)
    glfw.window_hint(glfw.GREEN_BITS, mode.bits.green)
    glfw.window_hint(glfw.BLUE_BITS, mode.bits.blue)
    glfw.window_hint(glfw.REFRESH_RATE, mode.refresh_rate)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    
    win = glfw.create_window(mode.size.width, mode.size.height, 'render', monitor, None)
    if not win:
        print 'GLFW: Window creation failed'
        glfw.terminate()
        exit()

    glfw.make_context_current(win)

    print 'Version:', glGetString(GL_VERSION)
    print 'Renderer:', glGetString(GL_RENDERER)

    rect_data = array.array('f', [
        -1.0, -1.0,
        1.0, -1.0,
        1.0, 1.0,
        -1.0, -1.0,
        1.0, 1.0,
        -1.0, 1.0,
    ])

    rect = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, rect)
    glBufferData(GL_ARRAY_BUFFER, rect_data.tostring(), GL_STATIC_DRAW)

    rect_zo_data = array.array('f', [
        0.0, 0.0,
        1.0, 0.0,
        1.0, 1.0,
        0.0, 0.0,
        1.0, 1.0,
        0.0, 1.0,
    ])

    rect_zo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, rect_zo)
    glBufferData(GL_ARRAY_BUFFER, rect_zo_data.tostring(), GL_STATIC_DRAW)

    samp_buf = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, samp_buf)
    glBufferData(GL_ARRAY_BUFFER, mapping[fixfmtsz:fixfmtsz+sigfmtsz], GL_STREAM_DRAW)
    glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 1, samp_buf)

    freq_buf = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, freq_buf)
    glBufferData(GL_ARRAY_BUFFER, STREAMS * 4, None, GL_STREAM_DRAW)
    glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 2, freq_buf)

    amp_buf = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, amp_buf)
    glBufferData(GL_ARRAY_BUFFER, STREAMS * 4, None, GL_STREAM_DRAW)
    glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 3, amp_buf)

    lin_buf = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, lin_buf)
    lin_arr = array.array('f', [(float(i) / options.map_samples) * 2.0 - 1.0 for i in range(options.map_samples)])
    #print lin_arr
    glBufferData(GL_ARRAY_BUFFER, lin_arr.tostring(), GL_STATIC_DRAW)

    bg_tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, bg_tex)
    bg_data = array.array('B', [0 for i in range(mode.size.width * mode.size.height)])
    glTexImage2D(GL_TEXTURE_2D, 0, GL_R8, mode.size.width, mode.size.height, 0, GL_RED, GL_UNSIGNED_BYTE, bg_data.tostring())
    glTexParameter(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameter(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glTexParameter(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameter(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)

    bg_swp = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, bg_swp)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_R8, mode.size.width, mode.size.height, 0, GL_RED, GL_UNSIGNED_BYTE, bg_data.tostring())
    glTexParameter(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameter(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glTexParameter(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameter(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)

    # Some *4s below because the texture is packed as RGBA8 despite only indexing R

    bar_pfac = mode.size.height / 128.0
    bg_bar_h = int(bar_pfac)
    bg_bar_sz = (bg_bar_h*4)

    block_d = '\x7f' * (64*64*4)
    clear_d = '\x00' * (mode.size.height*4)
    
    fbs = glGenFramebuffers(1)
    fbd = glGenFramebuffers(1)

    def make_prog(vss, fss):
        vs = glCreateShader(GL_VERTEX_SHADER)
        glShaderSource(vs, vss)
        glCompileShader(vs)
        if not glGetShaderiv(vs, GL_COMPILE_STATUS):
            print 'Vertex error:', glGetShaderInfoLog(vs)
            exit()

        fs = glCreateShader(GL_FRAGMENT_SHADER)
        glShaderSource(fs, fss)
        glCompileShader(fs)
        if not glGetShaderiv(fs, GL_COMPILE_STATUS):
            print 'Fragment error:', glGetShaderInfoLog(fs)
            exit()

        prog = glCreateProgram()
        glAttachShader(prog, vs)
        glAttachShader(prog, fs)
        glLinkProgram(prog)
        if not glGetProgramiv(prog, GL_LINK_STATUS):
            print 'Program error:', glGetProgramInfoLog(prog)
            exit()

        return prog

    prog_bg = make_prog('''
#version 430

in vec2 vPosition;
in vec2 vTex;

out vec2 vUV;

void main(void) {
    gl_Position = vec4(vPosition,0.0,1.0);
    vUV = vTex;
}''', '''
#version 430

in vec2 vUV;

layout (location = 0) out vec4 FragColor;
layout (std430, binding = 2) buffer bfreq {
    uint freq[];
};
layout (std430, binding = 3) buffer bamp {
    float amp[];
};

vec3 map_col(uint fr, float intensity) {
    if(fr == 0) return vec3(0.0,0.0,0.0);
    return vec3(
        0.66 * clamp((float(fr) - 40.0) / (1500.0 - 40.0), 0.0, 1.0),
        1.0,
        clamp(intensity, 0.0, 1.0)
    );
}

vec3 hsv2rgb(vec3 c)
{
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main(void) {
    float zox = (vUV.x + 1.0) / 2.0;
    uint v = uint(zox * freq.length());
    FragColor = vec4(
        hsv2rgb(map_col(freq[v], amp[v])),
        1.0
    );
}''')

    glUseProgram(prog_bg)
    vao_bg = glGenVertexArrays(1)
    glBindVertexArray(vao_bg)
    glBindBuffer(GL_ARRAY_BUFFER, rect)
    a_vPosition = glGetProgramResourceLocation(prog_bg, GL_PROGRAM_INPUT, 'vPosition')
    print 'prog_bg a_vPosition', a_vPosition
    glVertexAttribPointer(a_vPosition, 2, GL_FLOAT, False, 0, None)
    glEnableVertexAttribArray(a_vPosition)
    a_vTex = glGetProgramResourceLocation(prog_bg, GL_PROGRAM_INPUT, 'vTex')
    print 'prog_bg a_vTex', a_vTex
    glVertexAttribPointer(a_vTex, 2, GL_FLOAT, False, 0, None)
    glEnableVertexAttribArray(a_vTex)

    prog_scope = make_prog('''
#version 430

in float vX;
in float vY;

void main(void) {
    gl_Position = vec4(vX, vY, 0.0, 1.0);
}
''', '''
#version 430

layout (location = 0) out vec4 FragColor;

void main(void) {
    FragColor = vec4(0.0, 1.0, 0.0, 1.0);
}
''')

    glUseProgram(prog_scope)
    vao_scope = glGenVertexArrays(1)
    glBindVertexArray(vao_scope)
    glBindBuffer(GL_ARRAY_BUFFER, lin_buf)
    a_vX = glGetProgramResourceLocation(prog_scope, GL_PROGRAM_INPUT, 'vX')
    print 'prog_scope a_vX', a_vX
    glVertexAttribPointer(a_vX, 1, GL_FLOAT, False, 0, None)
    glEnableVertexAttribArray(a_vX)
    glBindBuffer(GL_ARRAY_BUFFER, samp_buf)
    a_vY = glGetProgramResourceLocation(prog_scope, GL_PROGRAM_INPUT, 'vY')
    print 'prog_scope a_vY', a_vY
    glVertexAttribPointer(a_vY, 1, GL_FLOAT, False, 0, None)
    glEnableVertexAttribArray(a_vY)

    prog_bar = make_prog('''
#version 430

in vec2 vPosition;
in vec2 vTex;

out vec2 vUV;

void main(void) {
    gl_Position = vec4(vPosition, 0.0, 1.0);
    vUV = vTex;
}''', '''
#version 430

in vec2 vUV;

layout (location = 0) out vec4 FragColor;

uniform sampler2D uTex;

void main(void) {
    vec4 col = texture(uTex, vUV);
    FragColor = vec4(1.0, 1.0, 1.0, col.r);
}''')

    glUseProgram(prog_bar)
    vao_bar = glGenVertexArrays(1)
    glBindVertexArray(vao_bar)
    glBindBuffer(GL_ARRAY_BUFFER, rect)
    a_vPosition = glGetProgramResourceLocation(prog_bar, GL_PROGRAM_INPUT, 'vPosition')
    print 'prog_bar a_vPosition', a_vPosition
    glVertexAttribPointer(a_vPosition, 2, GL_FLOAT, False, 0, None)
    glEnableVertexAttribArray(a_vPosition)
    a_vTex = glGetProgramResourceLocation(prog_bar, GL_PROGRAM_INPUT, 'vTex')
    print 'prog_bar a_vTex', a_vTex
    glBindBuffer(GL_ARRAY_BUFFER, rect_zo)
    glVertexAttribPointer(a_vTex, 2, GL_FLOAT, False, 0, None)
    glEnableVertexAttribArray(a_vTex)
    u_uTex = glGetProgramResourceLocation(prog_bar, GL_UNIFORM, 'uTex')
    print 'prog_bar u_uTex', u_uTex
    glUniform1i(u_uTex, 0)
    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_2D, bg_tex)

    glClearColor(0.2, 0.0, 0.0, 1.0)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    while not glfw.window_should_close(win):
        glfw.make_context_current(win)
        glClear(GL_COLOR_BUFFER_BIT)

        arr = array.array('f')
        arr.fromstring(mapping[fixfmtsz:fixfmtsz+sigfmtsz])
        arr.byteswap()
        glBindBuffer(GL_ARRAY_BUFFER, samp_buf)
        glBufferSubData(GL_ARRAY_BUFFER, 0, arr.tostring())

        arr = array.array('I')
        arr.fromstring(mapping[fixfmtsz+sigfmtsz:])
        #print len(arr)
        arr.byteswap()
        glBindBuffer(GL_ARRAY_BUFFER, freq_buf)
        glBufferSubData(GL_ARRAY_BUFFER, 0, arr[::2].tostring())
        arr_fq = arr[::2]

        arr = array.array('f')
        arr.fromstring(mapping[fixfmtsz+sigfmtsz:])
        #print len(arr)
        arr.byteswap()
        glBindBuffer(GL_ARRAY_BUFFER, amp_buf)
        glBufferSubData(GL_ARRAY_BUFFER, 0, arr[1::2].tostring())
        arr_am = arr[1::2]

        #print len(arr_fq), len(arr_am)
        #print zip(arr_fq, arr_am)

        glBindFramebuffer(GL_READ_FRAMEBUFFER, fbs)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, fbd)
        glFramebufferTexture2D(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, bg_tex, 0)
        glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, bg_swp, 0)
        stat = glCheckFramebufferStatus(GL_READ_FRAMEBUFFER)
        if stat != GL_FRAMEBUFFER_COMPLETE:
            print 'Incomplete read buffer:', stat
        stat = glCheckFramebufferStatus(GL_DRAW_FRAMEBUFFER)
        if stat != GL_FRAMEBUFFER_COMPLETE:
            print 'Incomplete draw buffer:', stat
        glBlitFramebuffer(
            1, 0, mode.size.width, mode.size.height,
            0, 0, mode.size.width - 1, mode.size.height,
            GL_COLOR_BUFFER_BIT, GL_NEAREST
        )
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

        bg_swp, bg_tex = bg_tex, bg_swp
        glBindTexture(GL_TEXTURE_2D, bg_tex)
        glTexSubImage2D(GL_TEXTURE_2D, 0, mode.size.width - 1, 0, 1, mode.size.height, GL_RED, GL_UNSIGNED_BYTE, clear_d)
        for f, a in zip(arr_fq, arr_am):
            if f == 0:
                continue
            try:
                pitch = 12 * math.log(f / 440.0, 2) + 69
            except ValueError:
                pitch = 0
            bg_bar_d = chr(int(255 * max((0.0, min((1.0, a)))))) * bg_bar_sz
            glTexSubImage2D(GL_TEXTURE_2D, 0, mode.size.width - 1, int(pitch * bar_pfac), 1, bg_bar_h, GL_RED, GL_UNSIGNED_BYTE, bg_bar_d)
            #print 'plot', mode.size.width - 1, int(pitch * bg_bar_h), 1, bg_bar_h, repr(bg_bar_d)
            #glTexSubImage2D(GL_TEXTURE_2D, 0, mode.size.width - 64, int(pitch * bg_bar_h), 64, 64, GL_RED, GL_UNSIGNED_BYTE, block_d)

        #glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 64, 64, GL_RED, GL_UNSIGNED_BYTE, block_d)
        #glTexSubImage2D(GL_TEXTURE_2D, 0, mode.size.width - 64, mode.size.height - 64, 64, 64, GL_RED, GL_UNSIGNED_BYTE, block_d)

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, 0)

        glUseProgram(prog_bg)
        glBindVertexArray(vao_bg)
        glDrawArrays(GL_TRIANGLES, 0, 6)

        glUseProgram(prog_bar)
        glBindVertexArray(vao_bar)
        glBindTexture(GL_TEXTURE_2D, bg_tex)
        #print bg_tex, bg_swp
        #print glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_WIDTH), glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_HEIGHT)
        glEnable(GL_BLEND)
        glDrawArrays(GL_TRIANGLES, 0, 6)
        glDisable(GL_BLEND)
        glBindTexture(GL_TEXTURE_2D, 0)

        glUseProgram(prog_scope)
        glBindVertexArray(vao_scope)
        glDrawArrays(GL_LINE_STRIP, 0, options.map_samples)

        glfw.swap_buffers(win)
        glfw.poll_events()

    glfw.terminate()
