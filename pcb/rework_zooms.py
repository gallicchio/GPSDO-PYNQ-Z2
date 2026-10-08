#!/usr/bin/env python3
"""Zoom-ins of the board's 3D render, with the rework sites circled -- round 45.19.

    python3 pcb/rework_zooms.py            # writes gateware/board/rework_img/*.jpg

For gateware/board/BENCH_WIRING_OCXO.md, which is read at the soldering station.
It renders the committed board (rev A, as built) from both sides with KiCad's
`kicad-cli pcb render`, finds the board outline in each render, and maps board
millimetres to pixels from it.  So every mark sits at the coordinates the PCB file
gives, not where a hand put it.  The renders work on a copy of the board in a
temporary directory; nothing in the tree is opened for writing.

kicad-cli: $KICAD_CLI (a command, split on spaces), or the KiCad 10 AppImage in
~/.local/bin.
"""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
BOARD = os.path.join(PROJ, 'GPSDO-PYNQ-Z2.kicad_pcb')
OUT = os.path.join(PROJ, 'gateware', 'board', 'rework_img')
W_MM, H_MM = 207.0, 180.0
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
RED, YEL, CYAN, WHITE = (255, 40, 40), (255, 230, 0), (0, 230, 255), (255, 255, 255)

# Each zoom: file, side, title, centre (mm), size (mm), marks.
# Marks: ('c', x, y, r_mm, colour, label, label_dx_mm, label_dy_mm)  a circle
#        ('l', x1, y1, x2, y2, colour, label, label_dx_mm, label_dy_mm)  a line
ZOOMS = [
    ('s1_unit10_top', 'top', 'S1: unit 10: SMA J1001 and 50R header JP1001', (157.0, 124.0), 28, [
        ('c', 164.1, 125.0, 4.4, RED, 'SMA J1001 (jack "10")', -12, -7.5),
        ('c', 151.63, 121.6, 2.4, YEL, 'header JP1001, then a shunt', -12, -5),
    ]),
    ('s1_unit10_bottom', 'bottom', 'S1 from underneath: solder J1001 and JP1001 here', (157.0, 124.0), 28, [
        ('c', 164.1, 125.0, 4.4, RED, 'J1001: 5 pins', -6, -7.5),
        ('c', 151.63, 121.6, 2.4, YEL, 'JP1001: 2 pins', -8, -5),
    ]),
    ('s2_unit3', 'top', 'S2: park unit 3: 100 kOhm from TP302 (S) to JP301 pin 2 (GND)', (58.5, 62.9), 24, [
        ('c', 60.3, 59.7, 1.3, RED, 'TP302 = S', 1.8, -2.8),
        ('c', 56.64, 66.1, 1.3, CYAN, 'JP301 pin 2 = GND', -2, 2.2),
        ('l', 60.3, 59.7, 56.64, 66.1, YEL, '100k', 0.8, 0.2),
    ]),
    ('s2_unit6', 'top', 'S2: park unit 6 (only if not S5): TP602 (S) to JP601 pin 2', (148.5, 89.2), 24, [
        ('c', 146.7, 92.4, 1.3, RED, 'TP602 = S', -7.5, 1.8),
        ('c', 150.36, 86.0, 1.3, CYAN, 'JP601 pin 2 = GND', -6, -3.6),
        ('l', 146.7, 92.4, 150.36, 86.0, YEL, '100k', 0.8, 0.2),
    ]),
    ('s2_unit7', 'top', 'S2: park unit 7: 100 kOhm from TP702 (S) to JP701 pin 2 (GND)', (58.5, 98.5), 24, [
        ('c', 60.3, 95.3, 1.3, RED, 'TP702 = S', 1.8, -2.8),
        ('c', 56.64, 101.7, 1.3, CYAN, 'JP701 pin 2 = GND', -2, 2.2),
        ('l', 60.3, 95.3, 56.64, 101.7, YEL, '100k', 0.8, 0.2),
    ]),
    ('s2_unit8', 'top', 'S2: park unit 8: 100 kOhm from TP802 (S) to JP801 pin 2 (GND)', (148.5, 107.0), 24, [
        ('c', 146.7, 110.2, 1.3, RED, 'TP802 = S', -7.5, 1.8),
        ('c', 150.36, 103.8, 1.3, CYAN, 'JP801 pin 2 = GND', -6, -3.6),
        ('l', 146.7, 110.2, 150.36, 103.8, YEL, '100k', 0.8, 0.2),
    ]),
    ('s2_unit13', 'top', 'S2b: park unit 13: 100 kOhm from TP1302 (S) to JP1301 pin 2 (GND)', (58.5, 151.9), 24, [
        ('c', 60.3, 148.7, 1.3, RED, 'TP1302 = S', 1.8, -2.8),
        ('c', 56.64, 155.1, 1.3, CYAN, 'JP1301 pin 2 = GND', -2, 2.2),
        ('l', 60.3, 148.7, 56.64, 155.1, YEL, '100k', 0.8, 0.2),
    ]),
    ('s3_fb401', 'top', 'S3: unit 4: FB401 (now a solder bridge) becomes 4.7 Ohm 0805', (145.0, 76.0), 24, [
        ('c', 142.76, 78.2, 2.0, RED, 'FB401 -> 4.7 Ohm', 2.5, 1.0),
        ('c', 143.9, 71.6, 2.2, CYAN, 'U401 (unit 4 squarer)', 2.8, -3.6),
    ]),
    ('s4_r3001_r3002', 'top', 'S4: by the TCXO: R3001 3k3 -> 1k, R3002 1k -> 330 Ohm', (101.0, 45.5), 24, [
        ('c', 101.25, 47.0, 1.8, RED, 'R3001 -> 1k', 2.3, -1.0),
        ('c', 98.1, 49.4, 1.8, YEL, 'R3002 -> 330', -6.5, 2.2),
        ('c', 103.3, 40.0, 3.2, CYAN, 'TCXO X3001', 3.6, -1.5),
    ]),
    ('s5_unit6_top', 'top', 'S5 (optional): unit 6: U601 -> 74AUP1GU04; SMA J601; header JP601', (153.0, 89.2), 30, [
        ('c', 143.9, 89.4, 2.4, RED, 'U601 -> 74AUP1GU04', -8, 3.0),
        ('c', 145.04, 90.35, 0.55, WHITE, 'pin 1', 1.0, 0.7),
        ('c', 164.1, 89.4, 4.4, RED, 'SMA J601 (jack "6")', -5, 5.0),
        ('c', 151.63, 86.0, 2.4, YEL, 'header JP601 + shunt', -10, -5.0),
    ]),
    ('s5_unit6_bottom', 'bottom', 'S5 from underneath: solder J601 and JP601 here', (153.0, 89.2), 30, [
        ('c', 164.1, 89.4, 4.4, RED, 'J601: 5 pins', -6, -7.5),
        ('c', 151.63, 86.0, 2.4, YEL, 'JP601: 2 pins', -8, -5),
    ]),
    ('jp201', 'top', 'Unit 2: fit a shunt on JP201 (it is off now)', (156.0, 52.0), 22, [
        ('c', 151.63, 50.4, 2.4, YEL, 'JP201: fit the shunt', -12, -5.0),
        ('c', 164.1, 53.8, 4.4, CYAN, 'J201 (jack "2", has an SMA)', -8, 5.5),
    ]),
]

# The overview: (label, x, y, colour)
OVERVIEW = [
    ('S1', 158.0, 123.5, RED), ('S2', 58.5, 62.9, YEL), ('S2', 148.5, 89.2, YEL),
    ('S2', 58.5, 98.5, YEL), ('S2', 148.5, 107.0, YEL), ('S2b', 58.5, 151.9, YEL), ('S3', 142.76, 78.2, RED),
    ('S4', 100.0, 48.0, RED), ('S5', 143.9, 89.4, CYAN), ('JP201', 151.63, 50.4, YEL),
]


def kicad_cli():
    env = os.environ.get('KICAD_CLI')
    if env:
        return shlex.split(env)
    return [os.path.expanduser('~/.local/bin/kicad-10.0.6-x86_64.AppImage'), 'kicad-cli']


def render(side, tmp):
    for ext in ('.kicad_pcb', '.kicad_pro'):
        shutil.copy(BOARD[:-len('.kicad_pcb')] + ext, tmp)
    out = os.path.join(tmp, 'render_%s.png' % side)
    subprocess.run(kicad_cli() + ['pcb', 'render', '-o', out, '-w', '9000', '-h', '7800',
                                  '--side', side, '--quality', 'basic', '--background', 'opaque',
                                  os.path.join(tmp, os.path.basename(BOARD))],
                   check=True, capture_output=True)
    return Image.open(out).convert('RGB')


def outline(im):
    """The board's pixel box: the render's background is a light blue-grey."""
    a = np.asarray(im).astype(int)
    bg = (a[:, :, 2] > a[:, :, 0] + 8) & (a.sum(2) > 330)
    xs = np.where((~bg).mean(0) > 0.5)[0]
    ys = np.where((~bg).mean(1) > 0.5)[0]
    return xs.min(), xs.max() + 1, ys.min(), ys.max() + 1


class Mapper:
    def __init__(self, box, side):
        self.x0, self.x1, self.y0, self.y1 = box
        self.s = (self.x1 - self.x0) / W_MM
        self.side = side
        sy = (self.y1 - self.y0) / H_MM
        assert abs(self.s / sy - 1) < 0.01, (self.s, sy)

    def __call__(self, x, y):
        if self.side == 'bottom':                 # seen from underneath: mirrored left-right
            x = W_MM - x
        return self.x0 + x * self.s, self.y0 + y * self.s


def label(d, xy, text, font, colour, size=None):
    """Text on a black box; kept inside an image of `size` (w, h)."""
    x, y = xy
    l, t, r, b = d.textbbox((x, y), text, font=font)
    if size:
        w, h = size
        x += max(0, 8 - l) - max(0, r - (w - 8))
        y += max(0, 8 - t) - max(0, b - (h - 8))
        l, t, r, b = d.textbbox((x, y), text, font=font)
    d.rectangle((l - 6, t - 4, r + 6, b + 4), fill=(0, 0, 0))
    d.text((x, y), text, font=font, fill=colour)


def wrap(d, text, font, width):
    lines, line = [], ''
    for word in text.split():
        trial = (line + ' ' + word).strip()
        if d.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def zoom(im, m, name, side, title, centre, size, marks):
    cx, cy = centre
    (px0, py0), (px1, py1) = m(cx - size / 2, cy - size / 2), m(cx + size / 2, cy + size / 2)
    box = (int(min(px0, px1)), int(min(py0, py1)), int(max(px0, px1)), int(max(py0, py1)))
    crop = im.crop(box).copy()
    d = ImageDraw.Draw(crop)
    s = m.s
    f = ImageFont.truetype(FONT, max(22, int(0.85 * s)))
    for mk in marks:
        if mk[0] == 'c':
            _, x, y, r, col, text, dx, dy = mk
            px, py = m(x, y)
            px, py = px - box[0], py - box[1]
            d.ellipse((px - r * s, py - r * s, px + r * s, py + r * s), outline=col, width=6)
        else:
            _, x1, y1, x2, y2, col, text, dx, dy = mk
            a, b = m(x1, y1), m(x2, y2)
            d.line((a[0] - box[0], a[1] - box[1], b[0] - box[0], b[1] - box[1]), fill=col, width=7)
            x, y = (x1 + x2) / 2, (y1 + y2) / 2
            px, py = m(x, y)
            px, py = px - box[0], py - box[1]
        if side == 'bottom':
            dx = -dx - 4                           # labels stay beside their mark when mirrored
        label(d, (px + dx * s, py + dy * s), text, f, col, crop.size)
    # title band (wrapped to the width) and an orientation note
    ft = ImageFont.truetype(FONT, max(20, int(0.72 * s)))
    fn = ImageFont.truetype(FONT, max(16, int(0.5 * s)))
    lines = wrap(d, title, ft, crop.width - 24)
    step = int(0.85 * s)
    band = 14 + step * len(lines) + int(0.7 * s)
    out = Image.new('RGB', (crop.width, crop.height + band), (20, 20, 20))
    out.paste(crop, (0, band))
    d = ImageDraw.Draw(out)
    for i, line in enumerate(lines):
        d.text((12, 8 + i * step), line, font=ft, fill=WHITE)
    note = ('board top edge is up; seen from the TOP' if side == 'top'
            else 'seen from UNDERNEATH (mirrored); board top edge is up')
    d.text((12, 10 + step * len(lines)), note, font=fn, fill=(200, 200, 200))
    if out.width > 1100:
        out = out.resize((1100, int(out.height * 1100 / out.width)), Image.LANCZOS)
    out.save(os.path.join(OUT, name + '.jpg'), quality=88)
    return name + '.jpg'


def overview(im, m):
    x0, x1, y0, y1 = m.x0, m.x1, m.y0, m.y1
    crop = im.crop((x0 - 40, y0 - 40, x1 + 40, y1 + 40)).copy()
    d = ImageDraw.Draw(crop)
    s = m.s
    f = ImageFont.truetype(FONT, int(2.4 * s))
    for text, x, y, col in OVERVIEW:
        px, py = m(x, y)
        px, py = px - x0 + 40, py - y0 + 40
        r = 4.5 * s
        d.ellipse((px - r, py - r, px + r, py + r), outline=col, width=14)
        label(d, (px + r + 10, py - 1.2 * s), text, f, col)
    w = 1600
    crop = crop.resize((w, int(crop.height * w / crop.width)), Image.LANCZOS)
    crop.save(os.path.join(OUT, 'overview.jpg'), quality=85)


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='rework_zooms_')
    try:
        ims = {side: render(side, tmp) for side in ('top', 'bottom')}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    maps = {side: Mapper(outline(im), side) for side, im in ims.items()}
    overview(ims['top'], maps['top'])
    for name, side, title, centre, size, marks in ZOOMS:
        print(zoom(ims[side], maps[side], name, side, title, centre, size, marks))
    print('overview.jpg')
    return 0


if __name__ == '__main__':
    sys.exit(main())
