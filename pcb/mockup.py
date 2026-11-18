"""Floorplan mock-up for the round-15 proposal.  Draws only -- touches nothing.

Prompt 14, rotated 90 degrees so the board stays portrait and the PYNQ stays
where it is:

    1pps | 10 MHz |  H E L P E R  | 10 MHz | 1pps
    SMAs | blocks |   up the       | blocks | SMAs
         |        |   centre line  |        |
    <----- signal flows inward ----+----- inward ----->

Each unit is a horizontal strip: its 1 pps jack on the outer edge, its 10 MHz
jack next in, both chains running inward to meet the helper clock on the centre
line.  Seven units on the left, six on the right, interleaved in y so the
thirteen branch exits are evenly spaced down the helper band.

    python3 pcb/mockup.py out.png
"""
import sys, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

# ---- the proposal ---------------------------------------------------------
BW, BH = 185.0, 170.0            # BH unchanged, so the PYNQ relationship is too
XC = BW / 2.0
HB = 24.0                        # helper band width
B10_L, B10_W = 48.6, 16.8        # 10 MHz block: along the chain, across it
BPP_L, BPP_W = 25.4, 11.8        # 1 pps block
GAP = 1.5                        # between the pps block and the 10 MHz block
SMA_IN = 6.0                     # jack centre, in from the block's outer end
PITCH = 17.8                     # row pitch = 10 MHz block width + gutter
TOP = 26.0                       # top band: every cabled connector lives here
NL, NR = 7, 6

# ---- the PYNQ, unchanged --------------------------------------------------
PZ_W, PZ_H = 137.0, 87.0
PZ_BOTTOM = 76.0
OX, OY = PZ_W / 2.0 - BW / 2.0, PZ_BOTTOM + BH
def B(x, y):
    return (x - OX, OY - y)
HDR_X0, HDR_X1 = B(101.65 - 24.13, 0)[0], B(101.65 + 24.13, 0)[0]
HDR_Y = B(0, PZ_H - 3.5)[1]

rows_l = [TOP + PITCH / 2 + k * PITCH for k in range(NL)]
rows_r = [TOP + PITCH + k * PITCH for k in range(NR)]


def main(png):
    fig, ax = plt.subplots(figsize=(9.0, 11.0), dpi=120)
    ax.set_facecolor("#f7f7f2")

    # PYNQ underneath
    p0, p1 = B(0, PZ_H), B(PZ_W, 0)
    ax.add_patch(Rectangle((p0[0], p0[1]), PZ_W, PZ_H, fill=True, fc="#dfe8f5",
                           ec="#5577aa", ls="--", lw=1.2, zorder=0))
    ax.text((p0[0] + p1[0]) / 2, p0[1] + PZ_H - 16, "PYNQ-Z2  137 x 87 mm\n"
            "unchanged: same 11 mm overlap,\nsame two shared M3 standoffs",
            ha="center", va="top", color="#3a5f8a", fontsize=8)
    ax.plot([HDR_X0, HDR_X1], [HDR_Y, HDR_Y], color="#cc7700", lw=6,
            solid_capstyle="butt", zorder=3)
    ax.text((HDR_X0 + HDR_X1) / 2, HDR_Y - 3.5, "RPi 2x20 socket (underside)",
            ha="center", fontsize=7.5, color="#aa5500")

    # our board
    ax.add_patch(Rectangle((0, 0), BW, BH, fill=True, fc="#ffffff",
                           ec="#111111", lw=2.0, zorder=1))

    # helper band
    ax.add_patch(Rectangle((XC - HB / 2, TOP), HB, BH - TOP - 20.0, fc="#ffe9c9",
                           ec="#cc8800", lw=1.2, zorder=2))
    ax.text(XC, TOP + 5, "HELPER\nTCXO\nSi5351\nsquarer", ha="center",
            va="top", fontsize=7, color="#8a5a00")

    def unit(u, y, side):
        s = 1 if side == "R" else -1
        x10 = XC + s * HB / 2 if s > 0 else XC - HB / 2 - B10_L
        ax.add_patch(Rectangle((x10, y - B10_W / 2), B10_L, B10_W, fc="#dff0d8",
                               ec="#4a8a3a", lw=1.0, zorder=3))
        xpp = (x10 + B10_L + GAP) if s > 0 else (x10 - GAP - BPP_L)
        ax.add_patch(Rectangle((xpp, y - BPP_W / 2), BPP_L, BPP_W, fc="#e8e0f5",
                               ec="#6a4a9a", lw=1.0, zorder=3))
        sx10 = (x10 + B10_L - SMA_IN) if s > 0 else (x10 + SMA_IN)
        sxpp = (xpp + BPP_L - SMA_IN) if s > 0 else (xpp + SMA_IN)
        for sx, c in ((sx10, "#2a6a1a"), (sxpp, "#4a2a7a")):
            ax.add_patch(Circle((sx, y), 4.75, fc="#ffffff", ec=c, lw=1.0,
                                zorder=4))
            ax.add_patch(Circle((sx, y), 1.3, fc=c, ec=c, zorder=5))
        ax.text(x10 + (B10_L / 2 if s > 0 else B10_L / 2), y, "%d" % u,
                ha="center", va="center", fontsize=7, color="#2a6a1a", zorder=6)

    for k, y in enumerate(rows_l):
        unit(1 + 2 * k if k < 7 else 0, y, "L")
    for k, y in enumerate(rows_r):
        unit(2 + 2 * k, y, "R")

    # top band: every cabled connector
    for i in range(5):
        ax.add_patch(Rectangle((5 + i * 12.5, 2), 11.0, 10.0, fc="#fde2e2",
                               ec="#aa3333", lw=1.0, zorder=3))
    ax.text(36, 15.5, "5 x 1-Wire probe screw terminals", ha="center",
            fontsize=7.5, color="#aa3333")
    ax.add_patch(Rectangle((72, 2), 16.0, 12.0, fc="#fff0cc", ec="#aa7700",
                           lw=1.0, zorder=3))
    ax.text(80, 17.5, "15 V jack", ha="center", fontsize=7, color="#aa7700")
    for i in range(2):
        ax.add_patch(Circle((94 + i * 6, 6), 2.2, fc="#fff0cc", ec="#aa7700",
                            zorder=3))
    ax.text(97, 12.5, "bench 5 V", ha="center", fontsize=7, color="#aa7700")
    ax.add_patch(Rectangle((106, 2), 74.0, 21.0, fc="#eeeeee", ec="#777777",
                           lw=1.0, ls=":", zorder=2))
    ax.text(143, 12.5, "POWER: fuses, OR-ing diodes, TVS,\n5.6 V clamp, 2 x LDO,"
            " heater FET", ha="center", va="center", fontsize=7.5, color="#555")

    # the fan-in band and the bottom blocks
    ax.add_patch(Rectangle((2, BH - 19.0), BW - 4, 8.0, fc="#f0f0ff",
                           ec="#8888bb", lw=1.0, ls=":", zorder=2))
    ax.text(52, BH - 15.0, "beat / pulse fan-in", ha="center", va="center",
            fontsize=7.5, color="#6666aa")

    # dimensions
    ax.annotate("", xy=(0, -7), xytext=(BW, -7),
                arrowprops=dict(arrowstyle="<->", color="#111"))
    ax.text(BW / 2, -10, "%.0f mm" % BW, ha="center", fontsize=9)
    ax.annotate("", xy=(-7, 0), xytext=(-7, BH),
                arrowprops=dict(arrowstyle="<->", color="#111"))
    ax.text(-10, BH / 2, "%.0f mm" % BH, va="center", ha="right", fontsize=9,
            rotation=90)

    # every 33R of the fan-out can sit beside the row it feeds
    for y in rows_l:
        ax.annotate("", xy=(XC - HB / 2 - 2, y), xytext=(XC - HB / 2 + 1, y),
                    arrowprops=dict(arrowstyle="->", color="#cc8800", lw=1.0))
    for y in rows_r:
        ax.annotate("", xy=(XC + HB / 2 + 2, y), xytext=(XC + HB / 2 - 1, y),
                    arrowprops=dict(arrowstyle="->", color="#cc8800", lw=1.0))
    ax.text(XC, BH - 26, "13 branches\n5-60 mm\n(was up to 110)", ha="center",
            fontsize=6.8, color="#8a5a00")
    ax.add_patch(Rectangle((XC - HB / 2 + 2, BH / 2 - 16), HB - 4, 32,
                           fc="#ffd9a0", ec="#aa6600", lw=1.0, zorder=3))
    ax.text(XC, BH / 2, "4 x buffer\nCLUSTERED\n(round 10)", ha="center",
            va="center", fontsize=6.5, color="#7a4a00", zorder=4)
    # half-width breakdown
    yb = BH + 6
    for x0, x1, lab in ((5.0, 30.4, "1 pps 25.4"), (31.9, 80.5, "10 MHz 48.6"),
                        (80.5, 104.5, "helper 24"), (104.5, 153.1, "10 MHz 48.6"),
                        (154.6, 180.0, "1 pps 25.4")):
        ax.annotate("", xy=(x0, yb), xytext=(x1, yb),
                    arrowprops=dict(arrowstyle="<->", color="#666", lw=0.8))
        ax.text((x0 + x1) / 2, yb + 4, lab, ha="center", fontsize=6.5,
                color="#444")
    ax.set_xlim(-28, BW + 18)
    ax.set_ylim(OY + 8, -26)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Round-15 proposal: helper up the centre, 10 MHz then 1 pps "
                 "either side\n%.0f x %.0f mm  (was 270 x 170)" % (BW, BH),
                 fontsize=10)

    fig.savefig(png, facecolor="#ffffff")
    print("wrote", png)
    print("new  %.0f x %.0f = %.0f mm2" % (BW, BH, BW * BH))
    print("old  270 x 170 = 45900 mm2   ->  %.0f%% smaller"
          % (100 * (1 - BW * BH / 45900.0)))


if __name__ == "__main__":
    main(sys.argv[1])
