width = 1280
height = 720

musicpath = ["/path/to/song/folder/"]

keycolor = (255, 0, 255) #chromakey color

#change this to change the gap between music nameplates
#27 is good for 1280 width in horizontal mode
gap = 27

bg = "tiles" #background mode (tiles, still, leave blank for chroma key)
bgpath = "/bg/example/path.png" #still background path

audio_out = None #audio output name, or None

horizontal = True #if true, the music names will scroll horizontally instead of vertically

bunnies = False #adds some jumping bunnies (or whatever you want) to the screen. i use an image of a bunny
bunnypath = "/path/to/image.png"

albumart = True #display album art on the next up list and in fullscreen mode

full = True #adds the music name and 3d album art

noframe = False #removes the window border

#the following only really apply to full mode:
visualizer = False #enable visualizer bars in the background
logo = True #toggles the pycube logo
antialias = True #antialiasing on the 3d album art

#metadata mode:
#0 - id3 only
#1 - id3, then .meta
#2 - .meta, then id3
#3 - .meta only
metadata = 2 #2 is the default

#.meta usage:
#if you have a song called "song.mp3", "song.mp3.meta" will contain the title on the first line and the artist on the second