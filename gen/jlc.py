"""JLCPCB's published capability, and the DRC we actually run against it.

Round 29.  Until now the numeric design rules were four values typed into
gen/gen.py -- clearance, track width, via diameter, via drill -- and KiCad's
own defaults filled in everything else.  KiCad's defaults are not JLCPCB's,
and two of them are looser: `min_copper_edge_clearance` defaults to 0.5 mm
(stricter, harmless) but `min_hole_clearance`, `min_silk_clearance` and the
whole silkscreen family default to values that let a board pass here and get
a DFM e-mail there.

So the table below is the single place the numbers live.  Each row is

    (kicad_rule_key, human name, jlc_min_mm, ours_mm, note)

and `rules()` emits `ours` into the .kicad_pro.  `ours` is never smaller than
`jlc` -- the assert at the bottom is the whole point of the file -- so a board
that passes our DRC is inside JLCPCB's capability by construction, usually
with a margin that is stated in the handbook table.

SOURCE of the jlc column: JLCPCB "PCB Capabilities" and "PCB Assembly
Capabilities", 4-layer FR-4, 1 oz outer / 0.5 oz inner, read 2026-09-14.
Where their published figure is a range that depends on copper weight or on
the "advanced" service, the STANDARD 4-layer figure is used, because that is
what mfg/make_fab.py tells the buyer to order.  Where they publish no figure
at all for a rule KiCad can check (solder-mask sliver is the only one), the
number is IPC-2221 class 2 and the note says so.
"""

# ---------------------------------------------------------------------------
# key                        name                       jlc    ours   note
# ---------------------------------------------------------------------------
RULES = [
 ("min_clearance",           "copper clearance",        0.0889, 0.15,
  "3.5 mil is JLC's 4-layer minimum; 0.15 is set by the finest pitch here, "
  "the Si5351C's 0.5 mm QFN-20 (rev A: an MSOP-10), whose own pads sit "
  "0.25 mm apart"),
 ("min_track_width",         "track width",             0.0889, 0.20,
  "every track on this board is 0.25 (signal) or 0.5 (power); 0.2 is the "
  "floor the DRC enforces"),
 ("min_via_diameter",        "via diameter",            0.40,   0.60,
  "one via size on the board: 0.6 mm pad, 0.3 mm drill"),
 ("min_via_annular_width",   "via annular ring",        0.13,   0.15,
  "(0.6 - 0.3)/2 = 0.15 exactly"),
 ("min_through_hole_diameter", "plated hole diameter",  0.20,   0.30,
  "smallest drill on the board is the 0.3 mm via; the SMA and header pins "
  "are 1.0-1.7 mm"),
 ("min_hole_clearance",      "hole to copper",          0.254,  0.254,
  "JLC's figure for a multilayer board, adopted unchanged"),
 ("min_hole_to_hole",        "hole edge to hole edge",  0.50,   0.50,
  "JLC's figure, adopted unchanged; round 28 made it an ERROR after two "
  "vias were drilled into through-hole pads and only warned"),
 ("min_copper_edge_clearance", "copper to board edge",  0.20,   0.30,
  "JLC routs to +/-0.2 mm, so 0.3 keeps copper off the bit"),
 ("min_silk_clearance",      "silkscreen to exposed copper", 0.15, 0.15,
  "JLC's own DFM check: ink over a solder-mask opening is SCRAPED OFF, so a "
  "clipped letter is not a warning, it is a missing letter"),
 ("min_text_height",         "silkscreen text height",  0.80,   0.80,
  "JLC print 0.8 mm; below that the strokes merge.  1.0 mm is their "
  "recommendation and is what every label on this board except the "
  "reference designators uses"),
 ("min_text_thickness",      "silkscreen stroke width", 0.1524, 0.155,
  "6 mil, and the one rule where the honest number is not round: every "
  "piece of text this project draws is 0.16 or more, and round 29 raises "
  "the stock footprints' own 0.12 mm graphic outlines to 0.16 as they are "
  "placed -- no KiCad rule checks a graphic line's width, only text's"),
 ("solder_mask_min_width",   "solder-mask sliver",      0.10,   0.10,
  "JLC publish no figure; 0.1 mm is IPC-2221 class 2 and is what their DFM "
  "flags in practice"),
]

# What must FAIL the build rather than merely be mentioned.  build.py runs
# `--severity-error`, so anything left at "warning" here is invisible to it --
# which is how round 28 shipped a board with 639 warnings and called it clean.
# Round 29 promotes everything JLCPCB would either reject or silently alter.
SEVERITIES = {
    # they will not build it
    "clearance":             "error",
    "copper_edge_clearance": "error",
    "hole_clearance":        "error",
    "hole_to_hole":          "error",
    "annular_width":         "error",
    "drill_out_of_range":    "error",
    "track_width":           "error",
    "shorting_items":        "error",
    "tracks_crossing":       "error",
    "solder_mask_bridge":    "error",
    "unconnected_items":     "error",
    # they will build it and it will be wrong
    "silk_over_copper":      "error",   # ink over a mask opening is scraped off
    "text_height":           "error",
    "text_thickness":        "error",
    "silk_edge_clearance":   "error",   # ink off the edge of the board
    # assembly
    "courtyards_overlap":    "error",
    "malformed_courtyard":   "error",
    "footprint_type_mismatch": "error",
    # deliberate on this board, and argued for in the round where it was set
    "silk_overlap":          "warning",  # two labels touching is ugly, not fatal
    "track_dangling":        "warning",  # the +3V3_A spines end in open stubs
    "via_dangling":          "warning",  # ground vias in the F.Cu pour
    "isolated_copper":       "warning",
    "starved_thermal":       "warning",
    "lib_footprint_mismatch": "ignore",  # the library IS generated from here
    "lib_footprint_issues":  "ignore",
}


def rules():
    """The `rules` block for the .kicad_pro."""
    return {k: ours for k, _n, _j, ours, _w in RULES}


def severities():
    return dict(SEVERITIES)


def table():
    """[(name, jlc, ours, margin_str, note)] for the handbook."""
    out = []
    for _k, name, jlc, ours, note in RULES:
        if ours == jlc:
            margin = "as JLC"
        else:
            margin = "%.0f%% over" % (100.0 * (ours / jlc - 1.0))
        out.append((name, jlc, ours, margin, note))
    return out


for _k, _n, _jlc, _ours, _w in RULES:
    assert _ours >= _jlc, (
        "%s: our DRC (%g) is LOOSER than JLCPCB's capability (%g); the point "
        "of this file is that it cannot be" % (_k, _ours, _jlc))

# Silkscreen line width.  KiCad's stock footprints draw their outlines at
# 0.12 mm, which is below JLCPCB's 6 mil minimum, and no KiCad DRC rule checks
# a GRAPHIC line's width -- only text.  pcb/build_pcb.footprint() raises every
# F.SilkS/B.SilkS stroke below this as the footprint is placed.
SILK_LINE_MIN = 0.16
