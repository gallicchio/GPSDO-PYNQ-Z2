"""Where KiCad is on this machine, for every build script -- REVB_CHANGES item 14.

The build runs on KiCad 10.  One place says where it is:

    APPDIR          the extracted AppImage (env KICAD_APPDIR),
                    default ~/.local/kicad10/AppDir
    SYMBOLS         its symbol libraries (env KICAD_SHARE overrides share/kicad)
    FOOTPRINTS      its footprint libraries
    kicad_cli()     the kicad-cli command, as a list (env KICAD_CLI)
    kicad_python()  KiCad's own Python, for scripts that import pcbnew
                    (env KICAD_PYTHON)

CLAUDE_PCB.md section 11: run the AppImage's Python as `AppDir/AppRun python3.11`;
calling usr/bin/python3.11 directly with LD_LIBRARY_PATH set segfaults on
`import pcbnew` (10.0.6).

KiCad 10 keeps each symbol library as a directory of one-symbol files
(`Lib.kicad_symdir/Name.kicad_sym`); KiCad 9 kept one file per library.
gen/kigen.py reads both.
"""
import os
import shlex

APPDIR = os.environ.get("KICAD_APPDIR", os.path.expanduser("~/.local/kicad10/AppDir"))
SHARE = os.environ.get("KICAD_SHARE", os.path.join(APPDIR, "usr", "share", "kicad"))
SYMBOLS = os.path.join(SHARE, "symbols")
FOOTPRINTS = os.path.join(SHARE, "footprints")


def kicad_cli():
    if os.environ.get("KICAD_CLI"):
        return shlex.split(os.environ["KICAD_CLI"])
    return [os.path.join(APPDIR, "AppRun"), "kicad-cli"]


def kicad_python():
    if os.environ.get("KICAD_PYTHON"):
        return shlex.split(os.environ["KICAD_PYTHON"])
    return [os.path.join(APPDIR, "AppRun"), "python3.11"]
