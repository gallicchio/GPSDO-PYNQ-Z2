#!/usr/bin/env python3
"""The diagram the top-level README shows (docs/images/readme_ddmtd.svg): how thirteen 10 MHz inputs become
picoseconds in a counter.

    python3 docs/readme_figures.py            write the SVG
    python3 docs/readme_figures.py --png DIR  also write a PNG into DIR, to look at

The numbers on it are HANDBOOK.md's: a 10.0012344 MHz helper, 1234.4 Hz beats, time stretched 8101 times,
12.34 ps a count.
"""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "images")
PNG_DIR = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
# the data-viz reference palette's first three hues, and its light-surface chrome
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE, INK, INK2, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#c3c2b7"


def ddmtd():
    W, Hh, U = 140, 70, 0.0845
    fig = plt.figure(figsize=(W * U, Hh * U))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, Hh); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, Hh, facecolor=SURFACE, edgecolor="none"))
    FT, FS = 11.0, 9.6

    def box(x, y, w, h, title, sub=None, fill="#ffffff"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.9", facecolor=fill, edgecolor=AXIS, linewidth=0.9))
        if sub:
            ax.text(x + w / 2, y + h * 0.65, title, ha="center", va="center", fontsize=FT, color=INK, fontweight="bold")
            ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=FS, color=INK2)
        elif title:
            ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=FT, color=INK, fontweight="bold")

    def arrow(p0, p1, color, lw=2.0):
        ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=11, color=color, linewidth=lw, shrinkA=0, shrinkB=0, zorder=3))

    def note(x, y, text, ha="center", bold=False):
        ax.text(x, y, text, ha=ha, va="center", fontsize=FS, color=INK if bold else INK2, fontweight="bold" if bold else "normal")

    def jack(x, y, label):
        ax.add_patch(FancyBboxPatch((x - 1.3, y - 1.3), 2.6, 2.6, boxstyle="round,pad=0,rounding_size=1.3", facecolor="#ffffff", edgecolor=INK2, linewidth=1.3))
        ax.text(x - 2.6, y, label, ha="right", va="center", fontsize=FS, color=INK, fontweight="bold")

    H = 8.6
    rows = [(58.5, "10 MHz, unit 1"), (46.5, "10 MHz, unit 2"), (27.5, "10 MHz, unit 13")]
    for y, name in rows:
        jack(22, y, name)
        box(27, y - H / 2, 16, H, "squarer", "to a logic level")
        box(48, y - H / 2, 18, H, "flip-flop", "samples the input")
        arrow((23.3, y), (27, y), ORANGE); arrow((43, y), (48, y), ORANGE); arrow((66, y), (92, y), BLUE)
    note(79, 60.4, "a 1234.4 Hz beat"); note(79, 48.4, "a 1234.4 Hz beat"); note(79, 29.4, "a 1234.4 Hz beat")
    for y in (39.4, 37.0, 34.6):
        ax.add_patch(FancyBboxPatch((56.4, y - 0.45), 0.9, 0.9, boxstyle="round,pad=0,rounding_size=0.45", facecolor=INK2, edgecolor="none"))
    # the helper clock, common to every channel
    box(4, 6, 19, H, "25 MHz TCXO", "on the board")
    box(27, 6, 22, H, "synthesizer", "10.0012344 MHz")
    arrow((23, 6 + H / 2), (27, 6 + H / 2), AQUA, lw=1.6)
    ax.plot([49, 57, 57], [6 + H / 2, 6 + H / 2, 23.2], color=AQUA, lw=1.6, solid_capstyle="round", zorder=3)
    arrow((57, 6 + H / 2), (57, 27.5 - H / 2), AQUA, lw=1.6)
    ax.plot([57, 70, 70], [18, 18, 18], color=AQUA, lw=1.6, solid_capstyle="round", zorder=3)
    arrow((70, 18), (92, 18), AQUA, lw=1.6)
    note(59.0, 8.4, "the helper clock: one for every flip-flop, and for the counter", ha="left")
    # the FPGA
    ax.add_patch(FancyBboxPatch((92, 12), 26, 52, boxstyle="round,pad=0,rounding_size=1.1", facecolor="#f3f2ee", edgecolor=AXIS, linewidth=0.9))
    ax.text(105, 60.2, "FPGA", ha="center", va="center", fontsize=12.5, color=INK, fontweight="bold")
    note(105, 57.4, "Zynq-7020, PYNQ-Z2")
    for k, s in enumerate(("a counter runs", "on the helper clock", "and is read at", "every beat edge")):
        note(105, 48.0 - 2.9 * k, s)
    note(105, 32.0, "one count is", bold=True); note(105, 29.0, "12.34 ps", bold=True); note(105, 26.0, "of input phase", bold=True)
    arrow((118, 38), (124, 38), INK2, lw=1.4)
    ax.text(125.2, 38, "Python:\nevery input\nagainst\nevery other", ha="left", va="center", fontsize=FS, color=INK, fontweight="bold", linespacing=1.4)
    # legend
    x = 2.5
    for c, s, w in ((ORANGE, "10 MHz", 19), (BLUE, "the same phase, 8101 times slower", 51), (AQUA, "helper clock: its own noise is in every channel alike, and cancels", 0)):
        ax.plot([x, x + 4], [67.0, 67.0], color=c, lw=2.4, solid_capstyle="round")
        ax.text(x + 5.2, 67.0, s, ha="left", va="center", fontsize=FS, color=INK2)
        x += w
    plt.rcParams["svg.hashsalt"] = "readme_ddmtd"
    fig.savefig(os.path.join(OUT, "readme_ddmtd.svg"), format="svg", bbox_inches="tight", pad_inches=0.12, facecolor=SURFACE, metadata={"Date": None})
    if PNG_DIR:
        fig.savefig(os.path.join(PNG_DIR, "readme_ddmtd.png"), dpi=110, bbox_inches="tight", pad_inches=0.12, facecolor=SURFACE)
    plt.close(fig)
    print("wrote docs/images/readme_ddmtd.svg")


if __name__ == "__main__":
    ddmtd()
