"""Paired image cleanup and exact GBA 4bpp/RGB555 conversion."""
import struct
from collections import deque
from pathlib import Path
from PIL import Image

SIZE = 64
PAIR_BYTES = 4128
EXPORT_VERSION = 4
INK = (32, 32, 48)


def canonical(root, catalog, species, view, shiny=False):
    folder = Path(root) / 'graphics/pokemon' / catalog[str(species)]['path']
    if not (folder / f'{view}.png').exists() and (folder / 'normal' / f'{view}.png').exists():
        folder = folder / 'normal'
    image = Image.open(folder / f'{view}.png')
    if image.mode == 'P':
        image.info['transparency'] = 0
        # The ROM applies the species palette to both tile sets. Some upstream
        # back PNGs retain obsolete embedded colors, so use the actual .pal.
        palette_path=folder / ('shiny.pal' if shiny else 'normal.pal')
        if palette_path.exists():
            colors = [list(map(int, line.split())) for line in palette_path.read_text().splitlines()[3:] if len(line.split()) == 3]
            image.putpalette([c for color in colors for c in color])
    return image.convert('RGBA').crop((0, 0, SIZE, SIZE))


def fit(image):
    image = image.convert('RGBA')
    if image.getchannel('A').getextrema()[0] == 255:
        # Only remove near-white pixels connected to the canvas edge.
        pixels = image.load()
        seen, queue = set(), deque()
        w, h = image.size
        for x in range(w):
            queue.extend(((x, 0), (x, h - 1)))
        for y in range(h):
            queue.extend(((0, y), (w - 1, y)))
        while queue:
            x, y = queue.popleft()
            if (x, y) in seen or not 0 <= x < w or not 0 <= y < h:
                continue
            seen.add((x, y))
            r, g, b, a = pixels[x, y]
            if min(r, g, b) < 230:
                continue
            pixels[x, y] = (r, g, b, 0)
            queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    box = image.getchannel('A').getbbox()
    if box is None:
        raise ValueError('generated sprite is empty')
    # A colored/gray backdrop can occupy less than 88% of the canvas and
    # otherwise pass the area check. Require a clean transparent outer border.
    alpha = image.getchannel('A')
    edges = ([alpha.getpixel((x,0)) for x in range(image.width)]
             + [alpha.getpixel((x,image.height-1)) for x in range(image.width)]
             + [alpha.getpixel((0,y)) for y in range(image.height)]
             + [alpha.getpixel((image.width-1,y)) for y in range(image.height)])
    if sum(value>=128 for value in edges)/len(edges) > .02:
        raise ValueError('generated image has a remaining background or a clipped creature')
    # Reject an unremoved full-canvas background instead of drawing a rectangle.
    opaque = sum(a >= 128 for a in image.getchannel('A').getdata())
    if opaque / (image.width * image.height) > .88:
        raise ValueError('generated background could not be separated')
    image = image.crop(box)
    # Integrate each destination pixel's coverage instead of sampling a single
    # arbitrary source pixel (which breaks thin ink lines and produces speckle).
    image.thumbnail((60, 60), Image.Resampling.BOX)
    output = Image.new('RGBA', (64, 64))
    output.paste(image, ((64 - image.width) // 2, 62 - image.height))
    output.putalpha(output.getchannel('A').point(lambda a: 255 if a >= 128 else 0))
    return output


def pixel_finish(image):
    """Finish the silhouette at native resolution, without resynthesizing anatomy.

    Remove only detached one/two-pixel debris. Retain larger islands and every
    connected appendage, including one-pixel antennae. Add a cardinal one-pixel
    ink contour outside the silhouette; diagonals don't get a thick square halo.
    """
    output = image.convert('RGBA').copy()
    if output.size != (SIZE, SIZE):
        raise ValueError('pixel finishing requires a 64x64 sprite')
    px = output.load()
    occupied = {(x,y) for y in range(SIZE) for x in range(SIZE) if px[x,y][3]>=128}
    remaining = set(occupied)
    while remaining:
        start = min(remaining)
        component, pending = {start}, [start]
        remaining.remove(start)
        while pending:
            x,y = pending.pop()
            for dx,dy in ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)):
                neighbor = (x+dx,y+dy)
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    pending.append(neighbor)
        if len(component)<=2:
            occupied.difference_update(component)
    if not occupied:
        raise ValueError('generated sprite contains only detached debris')
    for y in range(SIZE):
        for x in range(SIZE):
            if (x,y) not in occupied:
                px[x,y] = (0,0,0,0)
            else:
                px[x,y] = (*px[x,y][:3],255)
    contour = {(x+dx,y+dy) for x,y in occupied for dx,dy in ((-1,0),(1,0),(0,-1),(0,1))
               if 0<=x+dx<SIZE and 0<=y+dy<SIZE and (x+dx,y+dy) not in occupied}
    for x,y in contour:
        px[x,y] = (*INK,255)
    return output


def tiles(indices):
    output = bytearray()
    for ty in range(0, 64, 8):
        for tx in range(0, 64, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    a = indices[(ty + y) * 64 + tx + x]
                    b = indices[(ty + y) * 64 + tx + x + 1]
                    output.append(a | b << 4)
    return bytes(output)


def encode_canonical(front, back):
    """Preserve the native palette/pixels exactly; no AI or pixel finishing."""
    images=[front.convert('RGBA'),back.convert('RGBA')]
    colors=sorted({p[:3] for im in images for p in im.getdata() if p[3]})
    if len(colors)>15:raise ValueError('canonical pair exceeds GBA palette')
    lookup={rgb:i+1 for i,rgb in enumerate(colors)}
    binary=b''.join(tiles([lookup[p[:3]] if p[3] else 0 for p in im.getdata()]) for im in images)
    palette=[(0,0,0)]+colors+[(0,0,0)]*(15-len(colors))
    binary+=b''.join(struct.pack('<H',sum(((v*31+127)//255)<<(5*i) for i,v in enumerate(rgb))) for rgb in palette)
    validate(binary)
    return binary,images


def encode_pair(front, back):
    images = [front.convert('RGBA'), back.convert('RGBA')]
    if any(im.size != (64, 64) for im in images):
        raise ValueError('each view must be 64x64')
    opaque = [p[:3] for im in images for p in im.getdata() if p[3] >= 128]
    if not opaque:
        raise ValueError('empty sprite pair')
    # Reserve one shared ink color so palette reduction cannot wash out the
    # contour. All remaining colors are shared by both views, without dithering.
    fills = [p for p in opaque if p != INK] or [INK]
    sample = Image.new('RGB', (len(fills), 1))
    sample.putdata(fills)
    quantized = sample.quantize(colors=14, method=Image.Quantize.MEDIANCUT,
                                dither=Image.Dither.NONE)
    raw = quantized.getpalette()
    raw += [0] * max(0, 42 - len(raw))
    colors = [tuple((c >> 3) * 255 // 31 for c in INK)] + [
        tuple((raw[i + c] >> 3) * 255 // 31 for c in range(3)) for i in range(0, 42, 3)]
    palette = [(0, 0, 0)] + colors
    encoded, previews = [], []
    for im in images:
        indexes = []
        lookup = {}
        for r, g, b, a in im.getdata():
            if a < 128:
                indexes.append(0)
                continue
            rgb = (r, g, b)
            if rgb not in lookup:
                lookup[rgb] = 1 + min(range(15), key=lambda j: sum((rgb[k] - colors[j][k]) ** 2 for k in range(3)))
            indexes.append(lookup[rgb])
        encoded.append(tiles(indexes))
        preview = Image.new('RGBA', (64, 64))
        preview.putdata([(*palette[i], 255 if i else 0) for i in indexes])
        previews.append(preview)
    pal = b''.join(struct.pack('<H', ((r * 31 + 127) // 255) | ((g * 31 + 127) // 255) << 5 | ((b * 31 + 127) // 255) << 10) for r, g, b in palette)
    result = b''.join(encoded) + pal
    validate(result)
    return result, previews


def validate(payload):
    if len(payload) != PAIR_BYTES:
        raise ValueError('sprite payload must be exactly 4128 bytes')
    if any(value & 0x8000 for value in struct.unpack('<16H', payload[4096:])):
        raise ValueError('invalid RGB555 color')
    if payload[4096:4098] != b'\0\0':
        raise ValueError('palette index zero must be reserved')
