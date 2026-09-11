"""A two-layer grid maze router, used for everything that leaves a block.

Why a router at all: twenty-five beat/pulse returns converge on a 48 mm
connector from sources spread over 200 mm of board.  That is a planarity
problem, not an arithmetic one -- every hand-assigned lane plan leaves two or
three crossings somewhere -- and a maze router cannot produce a crossing,
because it only ever walks cells that are still free.

Why two layers: below the header the twenty-five returns need about sixteen
parallel lanes at the point where they converge, and the band between row B and
the socket is ten millimetres.  In2.Cu alone cannot hold them.  F.Cu down there
is empty (it is 100 mm from the nearest front end and the signals are a 1.2 kHz
beat and a 1 pps edge), so the router is allowed both layers and pays a via
cost to change.

Grid is 0.5 mm: a 0.25 mm track needs 0.4 mm centre-to-centre against a 0.15 mm
rule, so adjacent cells are legal and the grid never has to be finer.
"""
import heapq, math

PITCH = 0.5
NL = 2                     # layer 0 = In2.Cu, layer 1 = F.Cu
VIA_COST = 5.0
TURN_COST = 3.0


class Grid:
    def __init__(self, w, h, margin=1.0):
        self.nx, self.ny = int(w / PITCH) + 1, int(h / PITCH) + 1
        self.n = self.nx * self.ny
        self.blocked = [bytearray(self.n) for _ in range(NL)]
        m = int(margin / PITCH)
        for L in range(NL):
            b = self.blocked[L]
            for i in range(self.nx):
                for j in range(self.ny):
                    if i < m or j < m or i >= self.nx - m or j >= self.ny - m:
                        b[j * self.nx + i] = 1

    def cell(self, x, y):
        return (int(round(x / PITCH)), int(round(y / PITCH)))

    def pos(self, i, j):
        return (i * PITCH, j * PITCH)

    def _disc(self, L, x, y, r, v):
        # Distance is measured from the TRUE point, not from the cell it
        # rounds to.  Quantising the centre first under-blocks anything that
        # is off-grid by nearly half a cell, which is exactly what a stub
        # leaving a pad is, and it let routed tracks sit 0.13 mm from one.
        ci, cj = self.cell(x, y)
        n = int(math.ceil(r / PITCH)) + 1
        r2 = r * r
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i, j = ci + di, cj + dj
                if 0 <= i < self.nx and 0 <= j < self.ny:
                    if (i * PITCH - x) ** 2 + (j * PITCH - y) ** 2 <= r2:
                        for LL in ([L] if L is not None else range(NL)):
                            self.blocked[LL][j * self.nx + i] = v

    def block_disc(self, x, y, r, L=None):
        self._disc(L, x, y, r, 1)

    def free_disc(self, x, y, r, L=None):
        self._disc(L, x, y, r, 0)

    def block_seg(self, x0, y0, x1, y1, r, L=None):
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / (PITCH * 0.5)) + 1)
        for k in range(n + 1):
            t = k / float(n)
            self.block_disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, L)

    # -- A* over (cell, layer, direction) ---------------------------------
    def route(self, a, b, layers=(0,), start_layer=0, end_layer=None,
              turn=TURN_COST, cap=400000):
        """a, b are (x, y).  `layers` are the layers the route may use.
        Returns [(x, y, layer), ...] corners, or None."""
        s, t = self.cell(*a), self.cell(*b)
        end_layer = start_layer if end_layer is None else end_layer
        nx, ny = self.nx, self.ny
        blk = self.blocked
        DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
        best = {}
        h0 = abs(s[0] - t[0]) + abs(s[1] - t[1])
        pq = [(h0, 0.0, 0, s[0], s[1], start_layer, -1)]
        par = {}
        seen = 0
        while pq:
            seen += 1
            if seen > cap:
                return None
            f, g, _tie, i, j, L, d = heapq.heappop(pq)
            key = (i, j, L, d)
            if key in best:
                continue
            best[key] = g
            if (i, j) == t and L == end_layer:
                out, k = [], key
                while k is not None:
                    out.append((k[0] * PITCH, k[1] * PITCH, k[2]))
                    k = par.get(k)
                out.reverse()
                return _simplify(out)
            for nd, (di, dj) in enumerate(DIRS):
                ii, jj = i + di, j + dj
                if not (0 <= ii < nx and 0 <= jj < ny):
                    continue
                if blk[L][jj * nx + ii] and (ii, jj) != t:
                    continue
                nk = (ii, jj, L, nd)
                if nk in best:
                    continue
                ng = g + 1.0 + (turn if (d >= 0 and nd != d) else 0.0)
                par.setdefault(nk, key)
                heapq.heappush(pq, (ng + abs(ii - t[0]) + abs(jj - t[1]),
                                    ng, len(par), ii, jj, L, nd))
            for LL in layers:
                # A via is 0.6 mm plus clearance: the cell it lands on is not
                # enough, its four neighbours have to be clear on BOTH layers
                # too, or the barrel eats into whatever is one cell away.
                if LL == L or not self._via_ok(i, j):
                    continue
                nk = (i, j, LL, d)
                if nk in best:
                    continue
                ng = g + VIA_COST
                par.setdefault(nk, key)
                heapq.heappush(pq, (ng + abs(i - t[0]) + abs(j - t[1]),
                                    ng, len(par), i, j, LL, d))
        return None


    def _via_ok(self, i, j):
        for di, dj in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            ii, jj = i + di, j + dj
            if not (0 <= ii < self.nx and 0 <= jj < self.ny):
                return False
            k = jj * self.nx + ii
            for L in range(NL):
                if self.blocked[L][k]:
                    return False
        return True


def _simplify(pts):
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        ax, ay, al = out[-1]
        bx, by, bl = pts[k]
        cx, cy, cl = pts[k + 1]
        if bl != al or cl != bl:
            out.append(pts[k])
        elif (bx - ax) * (cy - by) != (by - ay) * (cx - bx):
            out.append(pts[k])
    out.append(pts[-1])
    return out
