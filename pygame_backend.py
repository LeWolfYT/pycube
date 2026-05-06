import pygame as pg
import vars as varr
import os
import threading as th
import random as r
from pygame._sdl2.mixer import set_post_mix
import statistics as st
import numpy as np
import math
import tinytag as tt
from io import BytesIO

def easeInOutSine(t):
    return -(math.cos(math.pi * t) - 1) / 2

audio_out = getattr(varr, "audio_out", None)
pg.mixer.pre_init(44100, -16, devicename=audio_out)
pg.init()

print(pg.mixer.get_init())

width = getattr(varr, "width", 1280)
height = getattr(varr, "height", 720)

visualize = False

#visualizer_base = pg.image.load("visualizer_base.png")
#visheight = visualizer_base.get_height()

window = pg.display.set_mode((width, height), pg.NOFRAME, vsync=True)
pg.display.set_caption("pyCube")

logo = pg.image.load("logo.png")

nameplate = pg.image.load("nameplate.png")
plateh = nameplate.get_height() #for when different size plate support is added
platew = nameplate.get_width()
separator = pg.image.load("bar.png")
separatorh = pg.image.load("bar_horiz.png")
imageplate = pg.image.load("imageplate.png")
imageplatemask = pg.image.load("imageplatemask.png")

futura = pg.font.Font("Futura.ttf", 40)
futura_condensed = pg.font.Font("Futura-CondensedMedium-Oblique.ttf", 45)
futura_small = pg.font.Font("Futura-Italic.ttf", 20)
blurmode = getattr(varr, "blurmode", "gaussian")

global textcache
textcache = {}

gap = getattr(varr, "gap", 25) #25 pixels

bgmode = getattr(varr, "bg", None)

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
if bgmode == "tiles":
    #find values
    #assuming each tile is 128x128
    tilesx = math.ceil(width / 128)
    tilesy = math.ceil(height / 128)
    bg = pg.Surface((tilesx*128, tilesy*128))
    #tiles will be loaded from musicloop
elif bgmode == "still":
    bgpath = getattr(varr, "bgpath", "bg.png")
    if os.path.exists(bgpath):
        bg = pg.image.load(bgpath)
        #find new dimensions
        aspect = bg.get_width() / bg.get_height()
        if aspect < width / height:
            #width is the limiting factor
            newwidth = width
            newheight = int(width / aspect)
        else:
            #height is the limiting factor
            newheight = height
            newwidth = int(height * aspect)
        bg = pg.transform.smoothscale(bg, (newwidth, newheight))
    else:
        print(f"Background image {bgpath} not found. Using chroma key.")
        bgmode = None

def musicloop():
    musicpath = getattr(varr, "musicpath")
    musicch = pg.mixer.Channel(0)
    global idx
    global idx_delayed
    global shuffle
    global bg
    idx = -1
    if musicpath:
        finalfiles = []
        finalinfo = []
        for path in musicpath:
            files = os.listdir(path)
            
            for file in files:
                #check for special files like .DS_Store and thumbs.db
                if file.startswith(".") or file == "Thumbs.db":
                    continue
                #get info
                if file.endswith(tt.TinyTag.SUPPORTED_FILE_EXTENSIONS):
                    try:
                        audiofile = tt.TinyTag.get(os.path.join(path, file), image=True)
                        if audiofile is not None:
                            img = audiofile.images.any
                            info = {
                                "title": audiofile.title or file,
                                "artist": audiofile.artist or None,
                                "album": audiofile.album or None
                            }
                            if img != None:
                                imsurf = pg.image.load(BytesIO(img.data))
                                info["coverimg"] = make_imageplate(imsurf)
                                info["coverraw"] = imsurf
                        else:
                            info = {"title": file, "artist": None, "album": None}
                    except Exception as e:
                        print(f"Error loading {file}: {e}")
                        info = {"title": file, "artist": None, "album": None}
                else:
                    info = {"title": file, "artist": None, "album": None}
                finalfiles.append(os.path.join(path, file))
                finalinfo.append(info)
                
        if len(finalfiles) > 0:
            if bgmode == "tiles":
                #load the tiles
                tiles_base = []
                for i in range(4):
                    tiles_base.append(pg.image.load(f"tiles/{i}.png"))
                pos_allowed = []
                for i in range(tilesx):
                    for j in range(tilesy):
                        #load a random tile
                        tile = tiles_base[r.randint(0, len(tiles_base)-1)]
                        #blit it to the background
                        bg.blit(tile, (i*128, j*128))
                        pos_allowed.append((i*128, j*128))
                for i in range(len(finalfiles)):
                    if "coverraw" in finalinfo[i]:
                        #load the image
                        img = finalinfo[i]["coverraw"]
                        #scale it to 128x128
                        img = pg.transform.smoothscale(img, (128, 128))
                        #blit it to the background at a random position
                        x, y = pos_allowed[r.randint(0, len(pos_allowed)-1)]
                        #remove the position from the list
                        pos_allowed.remove((x, y))
                        #blit the image
                        bg.blit(img, (x, y))
            c = list(zip(finalfiles, finalinfo))
            r.shuffle(c)
            finalfiles, finalinfo = zip(*c)
            while True:
                idx_delayed -= 1
                idx += 1
                idx = idx % len(finalfiles)
                file = finalfiles[idx]
                info = finalinfo[idx]
                #build the next up list (will be bigger than necessary but whatever)
                nextup.clear()
                nextup_info.clear()
                for i in range(len(finalfiles)):
                    nextup.append(finalfiles[(idx+i) % len(finalfiles)])
                    nextup_info.append(finalinfo[(idx+i) % len(finalfiles)])
                #play the music
                try:
                    musicch.play(
                        pg.mixer.Sound(file)
                    )
                except:
                    print(f"Error playing {file}")
                    continue
                while musicch.get_busy() and not shuffle:
                    pg.time.delay(100)
                    #it'll automatically break
                shuffle = False

def blur(surf: pg.Surface, radius):
    if blurmode == "box":
        return pg.transform.box_blur(surf, radius)
    elif blurmode == "gaussian":
        return pg.transform.gaussian_blur(surf, radius)
    elif blurmode == "dropshadow":
        
        transparent = pg.Surface((surf.get_width(), surf.get_height())).convert_alpha()
        transparent.fill((255, 255, 255, 0.5))
        transparent.blit(surf, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
        
        return transparent
    else:
        return pg.Surface((1, 1))

def expandSurface(surf, expansion):
    newsurf = pg.surface.Surface((surf.get_width() + expansion*2, surf.get_height() + expansion*2))
    newsurf.fill((255, 255, 255, 0))
    newsurf.blit(surf, (expansion, expansion))
    return newsurf

def alphablit(surf, alpha, coord):
    transparent = pg.surface.Surface((surf.get_width(), surf.get_height())).convert_alpha()
    transparent.fill((255, 255, 255, alpha))
    transparent.blit(surf, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
    window.blit(transparent, coord)

def alphablit2(surf, alpha, coord, dest):
    transparent = pg.surface.Surface((surf.get_width(), surf.get_height())).convert_alpha()
    transparent.fill((255, 255, 255, alpha))
    transparent.blit(surf, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
    dest.blit(transparent, coord)

def drawshadowtext(text, size, x, y, offset, shadow=127, totala=255, dest=window):
    text = str(text)
    usecache = True
    if text in textcache:
        if size in textcache[text]:
            textn = textcache[text][size][0]
            textsh = textcache[text][size][1]
            textbland = textcache[text][size][2]
        else:
            usecache = False
    else:
        usecache = False
    
    if totala != 255:
        usecache = False
    
    if not usecache:
        textn = size.render(text, 1, (255, 255, 255, 0))
        textsh = size.render(text, 1, (shadow/1.5, shadow/1.5, shadow/1.5, shadow))
        textsh = blur(expandSurface(textsh, 6), 4)
        
        if totala != 255:
            buf = pg.Surface((textsh.get_width(), textsh.get_height()))
            buf.fill((255, 255, 255))
            alphablit2(buf, 255-totala, (0, 0), textsh)
        
        
        if totala == 255:
            if not text in textcache:
                textcache[text] = {}
                textcache[text][size] = []
            if not size in textcache[text]:
                textcache[text][size] = []
            textcache[text][size].append(textn)
            textcache[text][size].append(textsh)
        textbland = size.render(text, 1, (255, 255, 255, 255))
        if totala == 255:
            textcache[text][size].append(textbland)
    
    if totala != 255:
        dest.blit(textsh, (x+offset, y+offset), special_flags=pg.BLEND_RGBA_MULT)
        alphablit2(textn, totala, (x, y), dest)
    else:
        dest.blit(textsh, (x+offset, y+offset), special_flags=pg.BLEND_RGBA_MULT)
        dest.blit(textn, (x, y))
    return textbland

def make_imageplate(img):
    scaled = pg.transform.smoothscale(img, (75, 75))
    new_surf = imageplate.copy()
    scaled.blit(imageplatemask, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
    new_surf.blit(scaled, (0, 0), special_flags=pg.BLEND_RGB_MULT)
    return new_surf

horizontal = getattr(varr, "horizontal", False)

bunnies = getattr(varr, "bunnies", False)
bunnypath = getattr(varr, "bunnypath", "bunny.png")

def draw_plate(text, delta=0, smalltext="", o=0):
    plate_surf = pg.Surface((300, 75), pg.SRCALPHA)
    plate_surf.blit(nameplate, (0, 0))
    
    offset = o #this is an offset since in horizontal mode there isn't enough room for the icon
    
    scroll = 0
    scroll2 = 0 #small text
    
    textsize = futura_condensed.size(text)
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

    if smalltext:
        textsize2 = futura_small.size(smalltext)
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
    
    drawshadowtext(text, futura_condensed, 5+scroll, 5, 0, dest=plate_surf)
    
    if smalltext:
        drawshadowtext(smalltext, futura_small, 8+scroll2, 45, 0, shadow=96, dest=plate_surf)
    return plate_surf

global visdata
visdata = [0 for _ in range(16)]

def average_buckets(arr, buckets):
    #this averages data into buckets buckets
    
    max = 65536
    array = []
    for i in range(0, len(arr), int(len(arr)/buckets)):
        array.append(st.mean(arr[i:i+int(len(arr)/buckets)])/max)
    return array

#we probably won't use average_buckets


def postmix_callback(postmix, memview):
    global visdata
    #print(type(memview), len(memview))
    #print(postmix)
    #do some housekeeping with the data since it's apparently S16 data and not whatever i thought it was
    
    raw = bytes(memview)
    rawnp = np.frombuffer(raw, dtype=np.uint16) #that's probably what our format is
    #convert to list
    raw2 = rawnp.tolist()
    
    final = average_buckets(raw2, 16)
    visdata = final

def draw_visualization():
    #it's a bar graph
    global visdata
    #max height is 55
    #padding on the left and right sides is 10, but 12 would be better
    #that gives 276 pixels to work with horizontally
    
    barwidth = 276/16
    maxheight = 55
    barpadding = 12
    ypadding = 10
    
    vis_surface = pg.Surface((300, 75), pg.SRCALPHA)
    
    for i in range(16):
        #draw the bar
        print(visdata[i])
        if round(visdata[i] * maxheight) > 0:
            barheight = maxheight * visdata[i]
            x = i * barwidth + barpadding
            y = maxheight - barheight + ypadding
            if visdata[i] < 0.333:
                color = (0, 255, 0)
            elif visdata[i] < 0.666:
                color = (255, 255, 0)
            else:
                color = (255, 0, 0)
            pg.draw.rect(vis_surface, color, (x, y, barwidth, barheight))
    
    return vis_surface

if visualize:
    set_post_mix(postmix_callback)

def main():
    global idx_delayed
    th.Thread(target=musicloop).start()
    
    tick = 0
    
    if bunnies:
        bunny = pg.image.load(bunnypath)
        
        bunnyc = 12
        bunnysize = width//bunnyc
        bunny = pg.transform.smoothscale(bunny, (bunnysize, bunnysize))
        
    
    clock = pg.time.Clock()
    
    showplates = True #for debugging purposes
    
    scroll = 0 #scrolling to the next song
    scrolling = False
    
    def calculate_plates():
        return math.ceil(height / (plateh + gap)) + (1 if scroll > 0 else 0) - (1 if visualize else 0)
    def calculate_plates_horizontal():
        return math.ceil(width / (platew + gap)) + (1 if scroll > 0 else 0) - (1 if visualize else 0)
    
    if not horizontal:
        seph = separator.get_height()
        sepw = separator.get_width()
        separatorsneeded = math.ceil(height / seph) #this is for filling a whole screen
        separatorsurf = pg.Surface((300, separatorsneeded*seph), pg.SRCALPHA)
        for i in range(separatorsneeded):
            separatorsurf.blit(separator, (300-sepw, i*seph))
    else:
        seph = separatorh.get_height()
        sepw = separatorh.get_width()
        separatorsneeded = math.ceil(width / sepw)
        separatorsurf = pg.Surface((separatorsneeded*sepw, 75), pg.SRCALPHA)
        for i in range(separatorsneeded):
            separatorsurf.blit(separatorh, (i*sepw, 0))
    
    while True:
        delta = clock.tick(60) / 1000.0
        tick += delta
        if idx_delayed < 0 and not scrolling:
            scrolling = True
            scroll = 0
        if scrolling:
            if horizontal:
                scroll += delta * (platew + gap)
                if scroll > (platew + gap):
                    idx_delayed += 1
                    scrolling = False
                    scroll = 0
            else:
                scroll += delta * (plateh + gap)
                if scroll > (plateh + gap):
                    idx_delayed += 1
                    scrolling = False
                    scroll = 0
            
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit()
                return
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    pg.quit()
                    return
                elif event.key == pg.K_SPACE:
                    #debugging key
                    showplates = not showplates
                elif event.key == pg.K_MINUS:
                    #shuffle
                    global shuffle
                    shuffle = True
        if bgmode == None:
            window.fill(getattr(varr, "keycolor", (255, 0, 255))) #chromakey color
        elif bgmode in ["tiles", "still"]:
            window.blit(bg, (0, 0))
        
        
        #draw the nameplates and separators
        
        #for i in range(len(nextup)):
        if nextup == []:
            continue
    
        # if visualize:
        #     window.blit(visualizer_base, (0, height-visheight))
        #     window.blit(draw_visualization(), (0, height-visheight))
        
        if not horizontal:
            window.blit(separatorsurf, (width-300, 0))
        else:
            window.blit(separatorsurf, (0, -25))
        
        plates = calculate_plates()
        if not horizontal:
            for i in range(plates):
                #they get stacked vertically, with later in the list on top
                yy = height-plateh - i*(plateh+gap) - ((plateh+gap) if visualize else 0) #100 since there's a 25 pixel separator
                if scrolling:
                    yy += round(easeInOutSine(scroll/(plateh+gap)) * (plateh+gap))
                #draw the plate
                if showplates:
                    window.blit(draw_plate(nextup_info[i + idx_delayed]["title"], tick, nextup_info[i + idx_delayed]["artist"] or nextup_info[i + idx_delayed]["album"] or ""), (width-300, yy))
                    if "coverimg" in nextup_info[i + idx_delayed]:
                        window.blit(nextup_info[i + idx_delayed]["coverimg"], (width-375, yy))
        else:
            plates = calculate_plates_horizontal()
            for i in range(plates):
                #they get stacked horizontally, with later in the list on the right
                xx = i*(platew+gap) + ((platew+gap) if visualize else 0)
                if scrolling:
                    xx -= round(easeInOutSine(scroll/(platew+gap)) * (platew+gap))
                #draw the plate
                if showplates:
                    window.blit(draw_plate(nextup_info[i + idx_delayed]["title"], tick, nextup_info[i + idx_delayed]["artist"] or nextup_info[i + idx_delayed]["album"] or "", 75 if "coverimg" in nextup_info[i + idx_delayed] else 0), (xx, 0))
                    if "coverimg" in nextup_info[i + idx_delayed]:
                        #this is positioned differently
                        window.blit(nextup_info[i + idx_delayed]["coverimg"], (xx + 300-75, 0))
        
        if bunnies:
            #draw the bunnies
            for i in range(bunnyc):
                #they jump up and down, so we can use absolute value of a sine wave
                x = i * bunnysize
                y = height - bunnysize - (math.fabs(math.sin(tick*4 - i/2) * 100))
                #draw the bunny
                window.blit(bunny, (x, y))
        #update the display
        if getattr(varr, "logo", False):
            window.blit(logo, (5, height-5-logo.get_height()))
        
        pg.display.flip()

main()