#!/bin/bash
# Render one region of a board as the fab prints it: white silkscreen and gold
# solder-mask openings on green, with the board edge in yellow.  Round 45.
#
#   pcb/silk_region.sh BOARD.kicad_pcb X0 Y0 W H OUT.png [DPI]
#
# X0 Y0 W H are board millimetres (KiCad's own coordinates, y down), e.g. the
# 1-Wire terminals:  pcb/silk_region.sh GPSDO-PYNQ-Z2.kicad_pcb 4 1 36 25 j6001.png
#
# Why not one `kicad-cli pcb export svg` of the top layers: in a single-layer
# plot the copper fill and the F.Fab text land on top of the silkscreen, in
# colours close to it, and the result is unreadable.  So each layer is plotted
# alone, recoloured, cropped by rewriting the SVG's viewBox (the plot keeps
# board coordinates in mm when --page-size-mode is 0), rasterised by Inkscape
# and stacked by ImageMagick.  Needs: KiCad 10's AppImage (or KICAD_APPIMAGE),
# inkscape, convert.
set -euo pipefail
if [ $# -lt 6 ]; then
    sed -n '2,10p' "$0"
    exit 2
fi
B=$1; X0=$2; Y0=$3; W=$4; H=$5; OUT=$6; DPI=${7:-200}
K=${KICAD_APPIMAGE:-$HOME/.local/bin/kicad-10.0.6-x86_64.AppImage}
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
for L in F.SilkS F.Mask Edge.Cuts; do
    timeout 180 "$K" kicad-cli pcb export svg --layers "$L" --mode-single \
        --exclude-drawing-sheet --page-size-mode 0 -o "$T/$L.svg" "$B" >/dev/null 2>&1
done
python3 - "$T" "$X0" "$Y0" "$W" "$H" <<'PY'
import re, sys
T, x0, y0, w, h = sys.argv[1], *map(float, sys.argv[2:])
# KiCad's default layer colours in the plot -> what the fab prints
for L, rep in (('F.SilkS', {'#F2EDA1': '#FFFFFF'}),
               ('F.Mask', {'#D864FF': '#C9A43B', '#FFFFFF': '#000000'}),
               ('Edge.Cuts', {'#D0D2CD': '#FFFF00'})):
    s = open('%s/%s.svg' % (T, L)).read()
    s, n = re.subn(r'width="[\d.]+mm" height="[\d.]+mm" viewBox="[^"]+"',
                   'width="%gmm" height="%gmm" viewBox="%g %g %g %g"'
                   % (w * 4, h * 4, x0, y0, w, h), s, count=1)
    if n != 1:
        sys.exit('%s: no viewBox to crop; did the KiCad SVG header change?' % L)
    for a, b in rep.items():
        s = s.replace(a, b)
    open('%s/%s_c.svg' % (T, L), 'w').write(s)
PY
for L in F.SilkS F.Mask Edge.Cuts; do
    # Inkscape 1.x hangs with a display and a session bus (CLAUDE_PCB.md section 11)
    env -u DISPLAY -u WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS=/dev/null timeout 120 \
        inkscape "$T/${L}_c.svg" --export-type=png --export-filename="$T/$L.png" \
        --export-dpi="$DPI" >/dev/null 2>&1
done
convert "$T/F.Mask.png" -background '#1E5A32' -flatten \
        "$T/F.SilkS.png" -composite "$T/Edge.Cuts.png" -composite "$OUT"
echo "$OUT"
