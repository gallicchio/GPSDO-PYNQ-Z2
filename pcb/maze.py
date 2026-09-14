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
    """Obstacles on a 0.5 mm grid, one plane per routing layer.

    `counted` makes each cell a REFERENCE COUNT rather than a flag, which is
    what lets a net's own copper be lifted out of a finished grid and put back
    exactly.  Without it the only safe way to route net N with its own pads open
    is to rebuild the whole grid from scratch with N left out -- 600 pads and
    2000 tracks rasterised into 2 x 148k cells, per net, per attempt -- and that
    is where a build spends 33 of its 40 minutes.  Setting a cell to 0 instead
    of decrementing it is the round-18 bug that this exists to avoid: freeing
    the disc round a pad also freed whatever else passed within a millimetre.

    In counted mode `free_disc` is meaningless and must not be called; use
    sub()/add() with the cell set an object contributed.
    """

    def __init__(self, w, h, margin=1.0, counted=False):
        self.nx, self.ny = int(w / PITCH) + 1, int(h / PITCH) + 1
        self.n = self.nx * self.ny
        self.counted = counted
        if counted:
            from array import array
            self.blocked = [array("H", bytes(2 * self.n)) for _ in range(NL)]
        else:
            self.blocked = [bytearray(self.n) for _ in range(NL)]
        m = int(margin / PITCH)
        for L in range(NL):
            b = self.blocked[L]
            for i in range(self.nx):
                for j in range(self.ny):
                    if i < m or j < m or i >= self.nx - m or j >= self.ny - m:
                        b[j * self.nx + i] = 1
        # Cells where a via's DRILL may not go, on any layer and for any net.
        # Separate from `blocked` because it is a different rule: hole-to-hole
        # spacing is about the drill, not the copper, and it applies even when
        # the pad in question belongs to the net being routed -- which is how
        # round 27's board came to have a via drilled inside J5001 pin 13
        # (0.000 mm hole-to-hole) and another 0.238 mm from J4001 pin 4.  Both
        # pads had been lifted out of `blocked` as the net's own copper, and
        # nothing else said a drill could not go there.
        self.novia = bytearray(self.n)

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

    # ---- counted mode: an object's cells, and add/sub on them -----------
    def cells_disc(self, x, y, r, L=None):
        ci, cj = self.cell(x, y)
        n = int(math.ceil(r / PITCH)) + 1
        r2 = r * r
        out = []
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i, j = ci + di, cj + dj
                if 0 <= i < self.nx and 0 <= j < self.ny:
                    if (i * PITCH - x) ** 2 + (j * PITCH - y) ** 2 <= r2:
                        k = j * self.nx + i
                        for LL in ([L] if L is not None else range(NL)):
                            out.append((LL, k))
        return out

    def cells_seg(self, x0, y0, x1, y1, r, L=None):
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / (PITCH * 0.5)) + 1)
        out = set()
        for k in range(n + 1):
            t = k / float(n)
            out.update(self.cells_disc(x0 + (x1 - x0) * t,
                                       y0 + (y1 - y0) * t, r, L))
        return out

    def cells_rect(self, x, y, rect, clr, L=None):
        hw, hh, ang = rect
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        rr = math.hypot(hw, hh) + clr
        ci, cj = self.cell(x, y)
        n = int(math.ceil(rr / PITCH)) + 1
        out = []
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i, j = ci + di, cj + dj
                if not (0 <= i < self.nx and 0 <= j < self.ny):
                    continue
                dx, dy = i * PITCH - x, j * PITCH - y
                ux, uy = dx * ca - dy * sa, dx * sa + dy * ca
                gx, gy = max(0.0, abs(ux) - hw), max(0.0, abs(uy) - hh)
                if gx * gx + gy * gy <= clr * clr:
                    k = j * self.nx + i
                    for LL in ([L] if L is not None else range(NL)):
                        out.append((LL, k))
        return out

    def add(self, cells):
        b = self.blocked
        for L, k in cells:
            b[L][k] += 1

    def sub(self, cells):
        b = self.blocked
        for L, k in cells:
            if b[L][k]:
                b[L][k] -= 1

    def block_disc(self, x, y, r, L=None):
        if self.counted:
            self.add(self.cells_disc(x, y, r, L))
            return
        self._disc(L, x, y, r, 1)

    def free_disc(self, x, y, r, L=None):
        self._disc(L, x, y, r, 0)

    def block_rect(self, x, y, rect, clr, L=None, v=1):
        """Block the cells within `clr` of a pad RECTANGLE.

        A pad is not a circle, and pretending it is one is expensive where it
        hurts most.  A SOIC-8 pad is 1.95 x 0.6 mm, so the half-diagonal model
        makes it a 2.04 mm disc: with 0.85 mm of clearance on top, every cell
        within 2.9 mm of every pin is blocked, which walls in the whole package
        and 2 mm of board around it.  Nothing can reach such a part's pins, and
        that -- not congestion -- is why the rails could not be finished.
        The real rectangle leaves the 0.97 mm of clear copper that is genuinely
        between two adjacent pins."""
        if self.counted:
            self.add(self.cells_rect(x, y, rect, clr, L))
            return
        hw, hh, ang = rect
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        rr = math.hypot(hw, hh) + clr
        ci, cj = self.cell(x, y)
        n = int(math.ceil(rr / PITCH)) + 1
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i, j = ci + di, cj + dj
                if not (0 <= i < self.nx and 0 <= j < self.ny):
                    continue
                dx, dy = i * PITCH - x, j * PITCH - y
                ux, uy = dx * ca - dy * sa, dx * sa + dy * ca
                gx, gy = max(0.0, abs(ux) - hw), max(0.0, abs(uy) - hh)
                if gx * gx + gy * gy <= clr * clr:
                    for LL in ([L] if L is not None else range(NL)):
                        self.blocked[LL][j * self.nx + i] = v

    def block_seg(self, x0, y0, x1, y1, r, L=None):
        if self.counted:
            self.add(self.cells_seg(x0, y0, x1, y1, r, L))
            return
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / (PITCH * 0.5)) + 1)
        for k in range(n + 1):
            t = k / float(n)
            self.block_disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, L)

    # -- A* over (cell, layer, direction) ---------------------------------
    def route(self, a, b, layers=(0,), start_layer=0, end_layer=None,
              turn=TURN_COST, cap=400000, strict_goals=False):
        """a is (x, y); b is (x, y) OR a list of them.

        A list makes it a multi-GOAL search, which is what a multi-terminal net
        needs: you want the nearest point of the tree so far, not the nearest
        other terminal, and the difference is the whole quality of a power
        distribution.  Returns [(x, y, layer), ...] corners, or None."""
        s = self.cell(*a)
        many = isinstance(b, (list, tuple, set)) and b and \
            isinstance(next(iter(b)), (list, tuple))
        goals = {self.cell(*q) for q in b} if many else {self.cell(*b)}
        if strict_goals:
            # A goal cell is allowed to be blocked, so the router can always
            # terminate on a pad or on its own stub.  For a multi-terminal net
            # the goal set is the whole tree -- hundreds of cells -- and any of
            # them that happened to be blocked by ANOTHER net became a legal
            # step.  Here the net's own copper is already unblocked, so a
            # blocked goal cell means somebody else is there: drop it.
            free = {g for g in goals
                    if not self.blocked[end_layer if end_layer is not None
                                        else start_layer][g[1] * self.nx + g[0]]}
            if free:
                goals = free
        t = min(goals, key=lambda g: abs(g[0] - s[0]) + abs(g[1] - s[1]))
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
            if (i, j) in goals and L == end_layer:
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
                if blk[L][jj * nx + ii] and (ii, jj) not in goals:
                    continue
                nk = (ii, jj, L, nd)
                if nk in best:
                    continue
                ng = g + 1.0 + (turn if (d >= 0 and nd != d) else 0.0)
                par.setdefault(nk, key)
                hh = min(abs(ii - g[0]) + abs(jj - g[1]) for g in goals) \
                    if len(goals) < 40 else 0
                heapq.heappush(pq, (ng + hh, ng, len(par), ii, jj, L, nd))
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
                hh = min(abs(i - g[0]) + abs(j - g[1]) for g in goals) \
                    if len(goals) < 40 else 0
                heapq.heappush(pq, (ng + hh, ng, len(par), i, j, LL, d))
        return None


    def block_via(self, x, y, r):
        """Forbid a via centre within r of (x, y).  Use for every through-hole
        drill: r = hole/2 + via drill/2 + the hole-to-hole rule."""
        ci, cj = self.cell(x, y)
        n = int(math.ceil(r / PITCH)) + 1
        r2 = r * r
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i, j = ci + di, cj + dj
                if 0 <= i < self.nx and 0 <= j < self.ny:
                    if (i * PITCH - x) ** 2 + (j * PITCH - y) ** 2 <= r2:
                        self.novia[j * self.nx + i] = 1

    def _via_ok(self, i, j):
        if self.novia[j * self.nx + i]:
            return False
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
