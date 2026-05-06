import pyray as rl
import vars as varr
import os
import threading as th
import random as r
import statistics as st
import math
import tinytag as tt
from io import BytesIO
import pytweening as pt
import hashlib as hl
import cffi
import numpy as np
import ctypes

def easeInOutSine(t):
    return -(math.cos(math.pi * t) - 1) / 2

audio_out = getattr(varr, "audio_out", None)
rl.init_audio_device()
SAMPLES = 1024
audio_buffer = np.zeros(SAMPLES, dtype=np.float32)
write_pos = 0

ffi = cffi.FFI()
ffi.cdef("void audio_callback(void * void_ptr, unsigned int frames);")

@ffi.callback("void(*)(void *, unsigned int)")
def audio_callback(void_ptr, frames):
    global write_pos, audio_buffer
    
    buffer_ptr = ctypes.cast(ctypes.c_void_p(int(ffi.cast("intptr_t", void_ptr))), ctypes.POINTER(ctypes.c_float))
    #print(type(frames))

    # Convert pointer -> numpy array
    samples = np.ctypeslib.as_array(
        ctypes.cast(buffer_ptr, ctypes.POINTER(ctypes.c_float)),
        shape=(frames*2,)  # stereo interleaved
    )

    # Downmix stereo to mono
    mono = samples.reshape(-1, 2).mean(axis=1)

    # Write into circular buffer
    n = len(mono)
    if n > SAMPLES:
        mono = mono[-SAMPLES:]
        n = SAMPLES
    end = (write_pos + n) % SAMPLES
    if write_pos + n < SAMPLES:
        audio_buffer[write_pos:write_pos+n] = mono
    else:
        split = SAMPLES - write_pos
        audio_buffer[write_pos:] = mono[:split]
        audio_buffer[:end] = mono[split:]
    write_pos = end

NUM_BARS = 16

def get_bars():
    spectrum = np.abs(np.fft.rfft(audio_buffer * np.hanning(SAMPLES)))
    spectrum = spectrum[:SAMPLES // 2]
    
    boost_exp = np.linspace(0.8, 40.0, SAMPLES//2) #arbitrary multipliers
    
    spectrum *= boost_exp

    freqs = np.fft.rfftfreq(SAMPLES, 1.0 / 44100)

    #not full hearing range, but i like it like this. also fixes weird band bugs
    band_edges = np.logspace(np.log10(100), np.log10(15000), NUM_BARS + 1)

    bands = np.zeros(NUM_BARS)
    for i in range(NUM_BARS):
        lo, hi = band_edges[i], band_edges[i+1]
        #fft bands
        idx = np.where((freqs >= lo) & (freqs < hi))[0]
        if len(idx) > 0:
            bands[i] = spectrum[idx].mean()
        else:
            bands[i] = -1

    if bands.max() > 20:
        bands /= bands.max()
    else:
        bands /= 20

    return bands

width = getattr(varr, "width", 1280)
height = getattr(varr, "height", 720)
full = getattr(varr, "full", False)
albumart = getattr(varr, "albumart", True)

bgmode = getattr(varr, "bg", None)

visualize2 = getattr(varr, "visualizer", True)

if visualize2:
    rl.attach_audio_mixed_processor(audio_callback)

visualize = False

flags = 0
if bgmode == "transparent":
    flags |= rl.ConfigFlags.FLAG_WINDOW_TRANSPARENT
if getattr(varr, "noframe", False):
    flags |= rl.ConfigFlags.FLAG_WINDOW_UNDECORATED
rl.set_config_flags(flags)
if getattr(varr, "antialias", False):
    rl.set_config_flags(rl.ConfigFlags.FLAG_MSAA_4X_HINT | flags)
rl.init_window(width, height, "pyCube")

logo = rl.load_texture("logo.png")

nameplate = rl.load_image("nameplate.png")
plateh = nameplate.height #for when different size plate support is added
platew = nameplate.width
separator = rl.load_image("bar.png")
separatorh = rl.load_image("bar_horiz.png")
imageplate = rl.load_image("imageplate.png")
imageplatemask = rl.load_image("imageplatemask.png")

fontsc = 1.5

text = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890~!@#$%^&*()-_+=ääüö,./;'[]\\<>?:\"{}| "

textcache = {}
textimagecache = {}

count = rl.ffi.new("int *", 0)
codes = rl.load_codepoints(text, count)

futura = rl.load_font_ex("Futura-Medium-Condensed-Oblique.otf", round(50*fontsc), None, 0)
futura_condensed = rl.load_font_ex("Futura-Medium-Condensed-Oblique.otf", round(45*fontsc), codes, count[0])
futura_small = rl.load_font_ex("Futura-Italic.ttf", round(20*fontsc), None, 0)

blurmode = getattr(varr, "blurmode", "gaussian")

global nameplatecache
nameplatecache = {}

gap = getattr(varr, "gap", 25) #25 pixels

global nextup
nextup = []
global nextup_info
nextup_info = []

global idx
idx = 0

global idx_delayed
idx_delayed = 0 #this is used to calculate the nameplates and such

global shuffle
shuffle = False #contrary to the name, it just skips the song

global bg #in case bg is not None
bg = None
if bgmode == "tiles":
    #find values
    #assuming each tile is 128x128
    tilesx = math.ceil(width / 128)
    tilesy = math.ceil(height / 128)
    #tiles will be loaded from musicloop
    bgt = rl.gen_image_color(tilesx*128, tilesy*128, rl.BLANK)
elif bgmode == "still":
    bgpath = getattr(varr, "bgpath", "bg.png")
    if os.path.exists(bgpath):
        bg = rl.load_texture(bgpath)
    else:
        print(f"Background image {bgpath} not found. Using chroma key.")
        bgmode = None

music_ready = False
stylish = 0
meta_mode = getattr(varr, "metadata", 2)

mmusic = None
bgt_ready = False
def musicloop():
    musicpath = getattr(varr, "musicpath")
    global idx
    global idx_delayed
    global shuffle
    global bg
    global bgt
    global stylish
    global mmusic
    global bgt_ready
    
    hashlist = {}
    idx = -1
    if musicpath:
        finalfiles = []
        finalinfo = []
        print("music path detected")
        for path in musicpath:
            #walk
            
            files = []
            print("walkin")
            for root, dirs, fils in os.walk(path):
                for file in fils:
                    fl = os.path.join(root, file)
                    if not os.path.exists(fl):
                        continue
                    if fl in fils:
                        continue
                    files.append(fl)
                    print(fl)
            print("walker done")
            #files = os.listdir(path)
            
            for file in files:
                #check for special files like .DS_Store and thumbs.db
                if os.path.basename(file).startswith(".") or os.path.basename(file) == "Thumbs.db" or os.path.basename(file).endswith(".txt") or os.path.basename(file).endswith(".meta"):
                    continue
                #get info
                if file.endswith(tt.TinyTag.SUPPORTED_FILE_EXTENSIONS):
                    try:
                        fullpath = os.path.join(path, file)
                        audiofile = tt.TinyTag.get(fullpath, image=True)
                        if audiofile is not None:
                            img = audiofile.images.any
                            title = None
                            artist = None
                            
                            if meta_mode in [0, 1]:
                                title = audiofile.title
                                artist = audiofile.artist
                                if title:
                                    title = title.strip()
                                if artist:
                                    artist = artist.strip()
                            if meta_mode in [1, 2, 3]:
                                if os.path.exists(fullpath+".meta"):
                                    with open(fullpath+".meta", "r") as f:
                                        meta = f.read().strip()
                                    if meta:
                                        lines = meta.split("\n")
                                        if len(lines) >= 1 and not title:
                                            title = lines[0]
                                        if len(lines) >= 2 and not artist:
                                            artist = lines[1]
                            if meta_mode == 2:
                                if not title:
                                    title = audiofile.title
                                if not artist:
                                    artist = audiofile.artist
                                if title:
                                    title = title.strip()
                                if artist:
                                    artist = artist.strip()
                                
                            info = {
                                "title": title or os.path.basename(file),
                                "artist": artist or None,
                                "album": audiofile.album or None
                            }
                            if img != None and albumart:
                                print("image!!!")
                                print()
                                imdata = BytesIO(img.data)
                                
                                #info["coverimg"] = make_imageplate(imsurf)
                                hash = hl.md5(imdata.getbuffer())
                                if hash in hashlist:
                                    info["covertex"] = None
                                    info["bigcovertex"] = None
                                    info["covertex"] = hashlist[hash]
                                else:
                                    imsurf = rl.load_image_from_memory(".jpg", imdata.getvalue(), len(imdata.getvalue()))
                                    info["covertex"] = None
                                    info["bigcovertex"] = None
                                    info["coverraw"] = imsurf
                                    hashlist[hash] = imsurf
                        else:
                            info = {"title": os.path.basename(file), "artist": None, "album": None}
                    except Exception as e:
                        print(f"Error loading {file}: {e}")
                        info = {"title": os.path.basename(file), "artist": None, "album": None}
                else:
                    info = {"title": os.path.basename(file), "artist": None, "album": None}
                finalfiles.append(os.path.join(path, file))
                finalinfo.append(info)
                
        if len(finalfiles) > 0:
            if bgmode == "tiles":
                #load the tiles
                tiles_base = []
                for i in range(4):
                    tiles_base.append(rl.load_image(f"tiles/{i}.png"))
                pos_allowed = []
                for i in range(tilesx):
                    for j in range(tilesy):
                        #load a random tile
                        tile = tiles_base[r.randint(0, len(tiles_base)-1)]
                        #blit it to the background
                        rl.image_draw(bgt, tile, rl.Rectangle(0, 0, 128, 128), rl.Rectangle(i*128, j*128, 128, 128), rl.WHITE)
                        #bg.blit(tile, (i*128, j*128))
                        pos_allowed.append((i*128, j*128))
                        print("allowed")
                bgt_ready = True
                for i in range(len(finalfiles)):
                    continue
                    if "coverraw" in finalinfo[i]:
                        #load the image
                        img = finalinfo[i]["coverraw"]
                        #scale it to 128x128
                        #img = rl.Transform
                        #blit it to the background at a random position
                        x, y = pos_allowed[r.randint(0, len(pos_allowed)-1)]
                        #remove the position from the list
                        pos_allowed.remove((x, y))
                        #blit the image
                        #rl.image_draw(bg, img, )
                        #bg.blit(img, (x, y))
                for tile in tiles_base:
                    rl.unload_image(tile)
                print("bgmode dun")
            
            print("bg load")
            c = list(zip(finalfiles, finalinfo))
            r.shuffle(c)
            finalfiles, finalinfo = zip(*c)
            
            print("musicch")
            
            while True:
                if mmusic is not None:
                    rl.stop_music_stream(mmusic)
                    rl.unload_music_stream(mmusic)
                print("music loop start")
                idx_delayed -= 1
                idx += 1
                stylish = 0
                idx = idx % len(finalfiles)
                file = finalfiles[idx]
                info = finalinfo[idx]
                #build the next up list (will be bigger than necessary but whatever)
                nextup.clear()
                nextup_info.clear()
                print("next up list building")
                for i in range(len(finalfiles)):
                    nextup.append(finalfiles[(idx+i) % len(finalfiles)])
                    nextup_info.append(finalinfo[(idx+i) % len(finalfiles)])
                print("list built")
                #play the music
                
                try:
                    mmusic = rl.load_music_stream(file)
                    mmusic.looping = False
                    rl.play_music_stream(mmusic)
                    print(f"playing {file}")
                except:
                    print(f"Error playing {file}")
                    continue
                while rl.is_music_stream_playing(mmusic) and not shuffle and not rl.window_should_close():
                    rl.wait_time(0.1)
                    #it'll automatically break
                if rl.window_should_close():
                    return
                shuffle = False

def blur(img, radius):
    return rl.image_blur_gaussian(img, radius)

def expandSurface(surf, expansion):
    newsurf = rl.gen_image_color(surf.width + expansion*2, surf.height + expansion*2, rl.BLANK)
    rl.image_draw(newsurf, surf, rl.Rectangle(0, 0, surf.width, surf.height), rl.Rectangle(expansion, expansion, surf.width, surf.height), rl.WHITE)
    #newsurf.blit(surf, (expansion, expansion))
    return newsurf

unload_at_render = []

def drawshadowtext(text, size, x, y, offset, shadow=127, totala=255, dest=None):
    shadow = 127
    if text == "":
        return
    global unload_at_render
    font = size[0]
    sz = size[1]*3/2
    if dest == None:
        if (text, size) not in textcache:
            ti = rl.image_text_ex(font, text, sz, 0, rl.Color(0, 0, 0, shadow))
            exp = expandSurface(ti, 6)
            blur(exp, 2)
            tx = rl.load_texture_from_image(exp)
            
            textcache[(text, size)] = tx
            rl.unload_image(ti)
            rl.unload_image(exp)
        else:
            tx = textcache[(text, size)]
        rl.draw_texture(tx, x+offset, y+offset, rl.WHITE)
        rl.draw_text_ex(font, text, (x, y), sz, 0, rl.Color(255, 255, 255, totala))
    elif dest == "M":
        if (text, size, "") not in textcache:
            ti = rl.image_text_ex(font, text, sz, 0, rl.Color(0, 0, 0, shadow))
            tl = rl.image_text_ex(font, text, sz, 0, rl.Color(255, 255, 255, 255))
            exp = expandSurface(ti, 6)
            blur(exp, 2)
            tx = rl.load_texture_from_image(exp)
            ty = rl.load_texture_from_image(tl)
            
            textcache[(text, size, "")] = (tx, ty)
            rl.unload_image(ti)
            rl.unload_image(exp)
    else:
        if (text, size) not in textimagecache:
            ti = rl.image_text_ex(font, text, sz, 0, rl.Color(0, 0, 0, shadow))
            exp = expandSurface(ti, 6)
            rl.unload_image(ti)
            blur(exp, 2)
            textimagecache[(text, size)] = exp
        else:
            exp = textimagecache[(text, size)]
        rl.image_draw(dest, exp, rl.Rectangle(0, 0, exp.width, exp.height), rl.Rectangle(x+offset, y+offset, exp.width, exp.height), rl.WHITE)
        
        #rl.image_draw_text_ex(dest, font, text, (x+offset, y+offset), sz, 0, rl.Color(0, 0, 0, shadow))
        rl.image_draw_text_ex(dest, font, text, (x, y), sz, 0, rl.Color(255, 255, 255, totala))

def drawshadowtextpro(text, size, offset, shadow=127, totala=255, bounding_source=None, bounding_dest=None, dest=None, s_offset=0):
    shadow = 127
    if text == "":
        return
    drawshadowtext(text, size, 0, 0, offset, shadow, totala, "M")
    tx, ty = textcache[(text, size, "")]
    
    x, y, width, height = bounding_source.x+offset, bounding_source.y+offset, bounding_source.width, bounding_source.height
    
    x2, y2, width2, height2 = bounding_dest.x, bounding_dest.y, bounding_dest.width, bounding_dest.height
    
    o = s_offset
    
    rl.draw_texture_pro(tx, rl.Rectangle(x, y, width+(tx.width - ty.width)-o, height+(tx.height - ty.height)), rl.Rectangle(x2, y2, width2+(tx.width - ty.width)-o, height2+(tx.height - ty.height)), (0, 0), 0, rl.WHITE)
    rl.draw_texture_pro(ty, bounding_source, bounding_dest, (0, 0), 0, rl.WHITE)

def drawshadowstretch(text, size, x, y, offset, shadow=127, totala=255, twidth=width):
    if text == "":
        return
    drawshadowtext(text, size, x, y, offset, shadow, totala, "M")
    tx, ty = textcache[(text, size, "")]
    
    mn = min(twidth, ty.width)
    ww = mn/ty.width
    
    rl.draw_texture_pro(tx, rl.Rectangle(0, 0, tx.width, tx.height), rl.Rectangle(x+offset, y+offset, int(tx.width*ww), tx.height), (0, 0), 0, rl.WHITE)
    rl.draw_texture_pro(ty, rl.Rectangle(0, 0, ty.width, ty.height), rl.Rectangle(x, y, int(ty.width*ww), ty.height), (0, 0), 0, rl.Color(255, 255, 255, totala))
    
    
def make_imageplate(img):
    newi = rl.image_copy(imageplate)
    rl.begin_blend_mode(rl.BlendMode.BLEND_MULTIPLIED)
    rl.image_draw(newi, img, rl.Rectangle(0, 0, img.width, img.height), rl.Rectangle(0, 0, newi.width, newi.height), rl.WHITE)
    rl.end_blend_mode()
    newt = rl.load_texture_from_image(newi)
    rl.unload_image(newi)
    return newt
    # scaled = pg.transform.smoothscale(img, (75, 75))
    # new_surf = imageplate.copy()
    # scaled.blit(imageplatemask, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
    # new_surf.blit(scaled, (0, 0), special_flags=pg.BLEND_RGB_MULT)
    # return new_surf

horizontal = getattr(varr, "horizontal", False)

bunnies = getattr(varr, "bunnies", False)
bunnypath = getattr(varr, "bunnypath", "bunny.png")

nameplatetx = rl.load_texture_from_image(nameplate)

def draw_plate(text, delta=0, smalltext="", o=0, pos=(0, 0)):
    global nameplatecache
    
    key = (text, smalltext)
    
    #plate_surf = rl.gen_image_color(300, 75, rl.BLANK)
    #rl.image_draw(plate_surf, nameplate, rl.Rectangle(0, 0, 300, 75), rl.Rectangle(0, 0, 300, 75), rl.WHITE)
    rl.draw_texture(nameplatetx, pos[0], pos[1], rl.WHITE)
    
    offset = o #this is an offset since in horizontal mode there isn't enough room for the icon
    
    scroll = 0
    scroll2 = 0 #small text
    
    textsize = rl.measure_text_ex(futura_condensed, text, 45, 0)
    textsize = (textsize.x+5, textsize.y)
    
    target_scroll = -textsize[0] + 290 - offset #account for 5 pixel padding
    
    if textsize[0] > (292 - offset): #extra 2 pixels to prevent scrolling text that's ever so slightly too long
        dt = (delta * 25) % 400
        if dt < 100:
            scroll = 0
        elif dt < 200:
            scroll = (dt-100)/100 * target_scroll
        elif dt < 300:
            scroll = target_scroll
        else:
            scroll = target_scroll - ((dt-300)/100 * target_scroll)
    
    if scroll == 0 and (textsize[0] <= (292 - offset)):
        drawshadowtext(text, (futura_condensed, 30), round(pos[0]+5), round(pos[1]+5), 0, dest=None)
    else:
        # too long
        tm = rl.measure_text_ex(futura_condensed, text, 45, 0).y

        text_t = min(-scroll, 5)
        text_t2 = min(textsize[0]+scroll, 300)

        draw_width = 300

        #clamp scroll so that src.x + draw_width does not exceed text width
        clamped_scroll = -scroll
        draw_width = min(draw_width, text_t2)
        #max_scroll = max(0, textsize[0] - draw_width)
        #clamped_scroll = min(max(-scroll, 0)+5, max_scroll)

        src = rl.Rectangle(clamped_scroll-text_t, 0, draw_width-(5-text_t), tm)
        dest = rl.Rectangle(round(pos[0]+5)-text_t, round(pos[1]+5), draw_width-(5-text_t), tm)

        drawshadowtextpro(text, (futura_condensed, 30), 0, bounding_source=src, bounding_dest=dest, dest=None, s_offset=12-(300-text_t2))
    
    if smalltext:
        textsize2 = rl.measure_text_ex(futura_small, smalltext, 30, 0)
        textsize2 = (textsize2.x+8, textsize2.y)
        target_scroll2 = -textsize2[0] + 284 - offset #8 pixel padding
        if textsize2[0] > 286: #text usually isn't too long but just in case
            dt2 = (delta * 25) % 400
            if dt2 < 100:
                scroll2 = 0
            elif dt2 < 200:
                scroll2 = (dt2-100)/100 * target_scroll2
            elif dt2 < 300:
                scroll2 = target_scroll2
            else:
                scroll2 = target_scroll2 - ((dt2-300)/100 * target_scroll2)
        
        if scroll2 == 0 and (textsize2[0] <= 286):
            drawshadowtext(smalltext, (futura_small, 20), round(pos[0]+8+scroll2), round(pos[1]+45), 0, shadow=96, dest=None)
        else:
            #too long
            tm = rl.measure_text_ex(futura_small, smalltext, 30, 0).y
            
            text2_t = min(-scroll2, 8)
            text2_t2 = min(textsize2[0]+scroll2, 300)
            
            draw_width = 300
            draw_width = min(draw_width, text2_t2)

            #clamp scroll so that src.x + draw_width does not exceed text width
            #max_scroll = max(0, textsize2[0] - draw_width)
            #clamped_scroll = min(max(-scroll2, 0), max_scroll)
            clamped_scroll2 = -scroll2
            
            src = rl.Rectangle(clamped_scroll2-text2_t, 0, draw_width-(8-text2_t), tm)
            dest = rl.Rectangle(round(pos[0]+8)-text2_t, round(pos[1]+45), draw_width-(8-text2_t), tm)
            
            drawshadowtextpro(smalltext, (futura_small, 20), 0, bounding_source=src, bounding_dest=dest, shadow=96, dest=None, s_offset=12)
    #plate_tex = rl.load_texture_from_image(plate_surf)
    #rl.unload_image(plate_surf)
    #return plate_tex

global visdata
visdata = [0 for _ in range(16)]

def average_buckets(arr, buckets):
    #this averages data into buckets buckets
    
    max = 65536
    array = []
    for i in range(0, len(arr), int(len(arr)/buckets)):
        array.append(st.mean(arr[i:i+int(len(arr)/buckets)])/max)
    return array

rl.set_target_fps(60)
def main():
    global idx_delayed
    th.Thread(target=musicloop).start()
    
    camera = rl.Camera3D(rl.Vector3(0, 0, 10), rl.Vector3(0, 0, 0), rl.Vector3(0, 1, 0), 45.0, 0)
    
    tick = 0
    
    if bunnies:
        bunnyi = rl.load_image(bunnypath)
        bunny = rl.load_texture_from_image(bunnyi)
        rl.unload_image(bunnyi)
        
        bunnyc = 12
        bunnysize = width//bunnyc
        #bunny = pg.transform.smoothscale(bunny, (bunnysize, bunnysize))
    
    showplates = True #for debugging purposes
    
    global stylish
    stylish = 0
    
    scroll = 0 #scrolling to the next song
    scrolling = False
    
    def calculate_plates():
        return math.ceil(height / (plateh + gap)) + (1 if scroll > 0 else 0) - (1 if visualize else 0)
    def calculate_plates_horizontal():
        return math.ceil(width / (platew + gap)) + (1 if scroll > 0 else 0) - (1 if visualize else 0)
    
    shiny = rl.load_shader("shaders/shiny.vs","shaders/shiny.fs")
    
    loc_light = rl.get_shader_location(shiny, "lightPos")
    loc_view = rl.get_shader_location(shiny, "viewPos")
    loc_light_color = rl.get_shader_location(shiny, "lightColor")
    rl.set_shader_value(shiny, loc_light_color, rl.Vector3(1.0, 1.0, 1.0), rl.ShaderUniformDataType.SHADER_UNIFORM_VEC3)
    rl.set_shader_value(shiny, loc_light, rl.Vector3(-4.5, 0, 0), rl.ShaderUniformDataType.SHADER_UNIFORM_VEC3)
    rl.set_shader_value(shiny, loc_view, rl.Vector3(0, 0, 10), rl.ShaderUniformDataType.SHADER_UNIFORM_VEC3)
    planem = rl.gen_mesh_plane(2, 2, 2, 2)
    plane = rl.load_model_from_mesh(planem)
    
    planeimg = rl.gen_image_gradient_linear(64, 64, 0, rl.BLUE, rl.PURPLE)
    planetex = rl.load_texture_from_image(planeimg)
    rl.unload_image(planeimg)
    
    plane.materials[0].maps.texture = planetex
    plane.materials[0].shader = shiny
    
    if not horizontal:
        seph = separator.height
        sepw = separator.width
        separatorsneeded = math.ceil(height / seph) #this is for filling a whole screen
        separatorsur = rl.gen_image_color(300, separatorsneeded*seph, rl.BLANK)
        for i in range(separatorsneeded):
            rl.image_draw(separatorsur, separator, rl.Rectangle(0, 0, separator.width, separator.height), rl.Rectangle(300-sepw, i*seph, separator.width, separator.height), rl.WHITE)
            #separatorsurf.blit(separator, (300-sepw, i*seph))
    else:
        seph = separatorh.height
        sepw = separatorh.width
        separatorsneeded = math.ceil(width / sepw)
        separatorsur = rl.gen_image_color(separatorsneeded*sepw, 75, rl.BLANK)
        for i in range(separatorsneeded):
            rl.image_draw(separatorsur, separatorh, rl.Rectangle(0, 0, separatorh.width, separatorh.height), rl.Rectangle(i*sepw, 0, separatorh.width, separatorh.height), rl.WHITE)
            #separatorsurf.blit(separatorh, (i*sepw, 0))
    separatorsurf = rl.load_texture_from_image(separatorsur)
    rl.unload_image(separatorsur)
    rl.unload_image(separator)
    rl.unload_image(separatorh)
    
    global unload_at_render
    
    bars = None
    bars_old = None
    
    bgg = None
    
    while not rl.window_should_close():
        if mmusic:
            rl.update_music_stream(mmusic)
        if rl.is_key_pressed(75): #40
            if not rl.is_window_fullscreen():
                rl.toggle_fullscreen()
        if visualize2:
            try:
                try:
                    bars_old = bars.copy()
                except:
                    pass
                if bars_old is None:
                    bars = get_bars()
                else:
                    bars = 0.5 * bars_old + 0.5 * get_bars()
            except RuntimeWarning:
                bars = None

            if bars_old is None:
                bars_old = bars.copy()
        for e in unload_at_render:
            if e[1] == "texture":
                rl.unload_texture(e[0])
        unload_at_render = []
        delta = rl.get_frame_time()
        #delta = 1
        tick += delta
        if idx_delayed < 0 and not scrolling:
            scrolling = True
            scroll = 0
        if scrolling:
            if horizontal:
                scroll += delta * (platew + gap) * abs(idx_delayed)
                if scroll > (platew + gap):
                    idx_delayed += 1
                    scrolling = False
                    scroll = 0
            else:
                scroll += delta * (plateh + gap) * abs(idx_delayed)
                if scroll > (plateh + gap):
                    idx_delayed += 1
                    scrolling = False
                    scroll = 0
        
        if rl.is_key_pressed(45):
            global shuffle
            shuffle = True
        if rl.is_key_pressed(32):
            showplates = not showplates
        if rl.is_key_pressed(83):
            stylish = 0
        
        rl.begin_drawing()
        
        rl.clear_background(rl.Color(*getattr(varr, "keycolor", (255, 0, 255))))
        if bgmode == "still":
            rl.draw_texture_pro(bg, rl.Rectangle(0, 0, bg.width, bg.height), rl.Rectangle(0, 0, width, height), (0, 0), 0, rl.WHITE)
        if bgmode == "tiles" and bgt_ready:
            if not bgg:
                bgg = rl.load_texture_from_image(bgt)
            rl.draw_texture(bgg, 0, 0, rl.WHITE)
            rl.draw_rectangle(0, 0, width, height, rl.Color(0, 0, 0, 50))
        elif bgmode == "transparent":
            #print("it's a fram!")
            rl.clear_background(rl.BLANK)
        
        #draw the nameplates and separators
        if nextup == []:
            continue
        
        if not horizontal:
            if not scrolling:
                rl.draw_texture(separatorsurf, width-300, 0, rl.WHITE)
            else:
                rl.draw_texture(separatorsurf, width-300, round(easeInOutSine(scroll/(plateh+gap)) * (separator.height * 3)), rl.WHITE)
                rl.draw_texture(separatorsurf, width-300, round(easeInOutSine(scroll/(plateh+gap)) * (separator.height * 3))-height, rl.WHITE)
        else:
            if not scrolling:
                rl.draw_texture(separatorsurf, 0, -25, rl.WHITE)
            else:
                rl.draw_texture(separatorsurf, -round(easeInOutSine(scroll/(platew+gap)) * (separatorh.width * 10)), -25, rl.WHITE)
                rl.draw_texture(separatorsurf, -round(easeInOutSine(scroll/(platew+gap)) * (separatorh.width * 10))+width, -25, rl.WHITE)
        
        ix = idx_delayed
        
        plates = calculate_plates()
        if not horizontal:
            for i in range(plates):
                #they get stacked vertically, with later in the list on top
                yy = height-plateh - i*(plateh+gap) - ((plateh+gap) if visualize else 0) #100 since there's a 25 pixel separator
                if scrolling:
                    yy += round(easeInOutSine(scroll/(plateh+gap)) * (plateh+gap))
                #draw the plate
                if showplates:
                    draw_plate(nextup_info[i + ix]["title"], tick, nextup_info[i + ix]["artist"] or nextup_info[i + ix]["album"] or "", pos=(width-platew, yy))

                    if albumart:
                        if "coverraw" in nextup_info[i + ix]:
                            if nextup_info[i + ix]["covertex"] is None:
                                nextup_info[i + ix]["covertex"] = make_imageplate(nextup_info[i + ix]["coverraw"])
                            rl.draw_texture(nextup_info[i + ix]["covertex"], width-375, yy, rl.WHITE)
        else:
            plates = calculate_plates_horizontal()
            for i in range(plates):
                #they get stacked horizontally, with later in the list on the right
                xx = i*(platew+gap) + ((platew+gap) if visualize else 0)
                if scrolling:
                    xx -= round(easeInOutSine(scroll/(platew+gap)) * (platew+gap))
                #draw the plate
                if showplates:
                    draw_plate(nextup_info[i + ix]["title"], tick, nextup_info[i + ix]["artist"] or nextup_info[i + ix]["album"] or "", 75 if "coverraw" in nextup_info[i + ix] else 0, pos=(xx, 0))

                    if albumart:
                        if "coverraw" in nextup_info[i + ix]:
                            if nextup_info[i + ix]["covertex"] is None:
                                nextup_info[i + ix]["covertex"] = make_imageplate(nextup_info[i + ix]["coverraw"])
                            rl.draw_texture(nextup_info[i + ix]["covertex"], xx+300-75, 0, rl.WHITE)
        
        if bunnies:
            #draw the bunnies
            for i in range(bunnyc):
                x = i * bunnysize
                y = height - bunnysize - (math.fabs(math.sin(tick*4 - i/2) * 100))
                #draw the bunny
                rl.draw_texture_pro(bunny, rl.Rectangle(0, 0, bunny.width, bunny.height), rl.Rectangle(x, y, bunnysize, bunnysize), (0, 0), 0, rl.WHITE)
        
        if full:
            if visualize2:
                if bars is not None:
                    screen_w = width
                    screen_h = height
                    bar_w = screen_w // (NUM_BARS * 2)

                    lbar = 0
                    for i, level in enumerate(bars):
                        if level >= 0:
                            lbar = level
                        x = (i * 2 + 1) * bar_w
                        try:
                            h = int(level * (screen_h - 50))
                        except ValueError:
                            h = 0
                        
                        rl.draw_rectangle(round(x-bar_w*0.5), screen_h - h, bar_w, h, rl.Color(0, 0, 0, 64))
            stylish += delta
            stylish = min(stylish, 1)
            smoothed = pt.easeOutQuad(stylish)
            if albumart:
                rl.begin_mode_3d(camera)
                
                rooot = pt.getPointOnLine(-235, 0, -55, 0, smoothed)[0]
                
                if "coverraw" in nextup_info[0]:
                    if not nextup_info[0]["bigcovertex"]:
                        nextup_info[0]["bigcovertex"] = rl.load_texture_from_image(nextup_info[0]["coverraw"])
                    plane.materials[0].maps.texture = nextup_info[0]["bigcovertex"]
                else:
                    plane.materials[0].maps.texture = planetex
                
                mat = rl.matrix_rotate_xyz((math.radians(90), 0, math.radians(rooot)))
                plane.transform = mat
                
                movefac = ((width/height)/0.25396825396)
                
                rl.draw_model(plane, rl.Vector3(-3.5 - (1-smoothed)*movefac, 0, 0), 2.0, rl.WHITE)
                mat = rl.matrix_rotate_xyz((math.radians(90), 0, math.radians(180+rooot)))
                plane.transform = mat
                rl.draw_model(plane, rl.Vector3(-3.5 - (1-smoothed)*movefac, 0, 0), 2.0, rl.WHITE)
                
                #mat = rl.matrix_rotate_xyz((math.radians(90), 0, math.radians(180+tick*20)))
                #plane.transform = mat
                #rl.draw_model(plane, rl.Vector3(-3.5, 0, 0), 2.0, rl.WHITE)
                
                #rl.draw_grid(10, 1.0)
                
                rl.end_mode_3d()
            
            if full:
                drawshadowstretch(nextup_info[0]["title"], (futura_condensed, 50), (int(width/2.56) if albumart else 10), int(height/2-80)+(1-smoothed)*20, 5, twidth=(width-(width/2.56 if albumart else 10)-10), totala=int(128+127*smoothed))
                drawshadowstretch(nextup_info[0]["artist"] or nextup_info[0]["album"] or "", (futura, 30), (int(width/2.56) if albumart else 10), int(height/2-10)+(1-smoothed)*20, 5, twidth=(width-(width/2.56 if albumart else 10)-10), totala=int(128+127*smoothed))
        
        #update the display
        if getattr(varr, "logo", False):
            rl.draw_texture(logo, 5, height-5-logo.height, rl.WHITE)
        
        rl.end_drawing()

main()