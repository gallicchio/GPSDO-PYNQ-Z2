#!/usr/bin/env python3
"""Pour the copper zones and write the result to a second file.

Run under KiCad's own Python, which is the only interpreter that has pcbnew:

    ~/.local/kicad10/AppDir/AppRun python3.11 mfg/fill_zones.py in.kicad_pcb out.kicad_pcb

(gen/kicad_env.py's kicad_python() says which interpreter build.py uses.)

DRC has to be run BOTH ways.  Unfilled it checks the tracks against each other;
filled it also checks them against the three ground pours, and that is the pass
that finds a track squeezed against a pour edge or an island of copper with no
connection.  Neither pass alone is sufficient, so build.py runs both.
"""
import sys
import pcbnew

src, dst = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(src)
zones = b.Zones()
pcbnew.ZONE_FILLER(b).Fill(zones)
b.BuildConnectivity()
pcbnew.SaveBoard(dst, b)
print("filled %d zones -> %s" % (len(list(zones)), dst))
