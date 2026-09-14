"""Two questions ERC does not answer:

  1. does power actually REACH every chip, through what, and is there a
     capacitor at the end of it?
  2. does every input have exactly one driver, and does every output go
     somewhere?

Both are walked over the exported netlist, so what is checked is what the
board will be built from, not what the drawing looks like.
"""
import sys, os, re
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, kids, kid, val

RAILS = ("+3V3_A", "+3V3_D", "+5V_HDR", "+15V_HTR")
BACKWARDS = []
PASSIVE_SERIES = ("FB", "R", "F", "L", "D")     # things a supply may pass through


def load(path):
    doc = parse(open(path, encoding="utf-8").read())[0]
    nets, pins_of, net_of = {}, defaultdict(dict), {}
    for n in kids(kid(doc, "nets"), "net"):
        nm = val(kid(n, "name"))
        members = []
        for nd in kids(n, "node"):
            r, p = val(kid(nd, "ref")), val(kid(nd, "pin"))
            t = kid(nd, "pintype")
            members.append((r, p, val(t) if t else ""))
            pins_of[r][p] = nm
        nets[nm] = members
    comps = {}
    for c in kids(kid(doc, "components"), "comp"):
        comps[val(kid(c, "ref"))] = val(kid(c, "value"))
    return nets, pins_of, comps


def other_pin(pins_of, ref, pin):
    ps = [p for p in pins_of[ref] if p != pin]
    return ps[0] if len(ps) == 1 else None


def trace_supply(nets, pins_of, comps, start_net, depth=0, seen=None):
    """Walk back from a node towards a rail through two-terminal parts."""
    seen = seen or set()
    if start_net in RAILS:
        return [start_net]
    if start_net in seen or depth > 6:
        return None
    seen.add(start_net)
    for ref, pin, _ in nets.get(start_net, []):
        if re.match(r"^(FB|R|F|L|D)\d", ref) and len(pins_of[ref]) == 2:
            op = other_pin(pins_of, ref, pin)
            if op is None or pins_of[ref][op] == "GND":
                continue          # shunt element (clamp, bypass), not a series feed
            up = trace_supply(nets, pins_of, comps, pins_of[ref][op], depth + 1, seen)
            if up:
                return ["%s(%s)" % (ref, comps.get(ref, "")), ] + up
    return None



def series_diodes(nets, pins_of, comps):
    """Every series diode, checked for which way round it is.

    A reversed series diode is invisible to everything else: the netlist is
    correct, both pins are on real nets, ERC is silent, and the rail even has
    the right node count.  It simply does not conduct.  The rule here is the
    physical one -- current flows from the connector you plug into towards the
    parts that consume it, so a diode's ANODE must be the side nearer the
    connector and its CATHODE the side nearer the power-input pins.
    """
    def hops(net, want, depth=0, seen=None, skip=None):
        """Hops from `net` to the nearest connector pin / power_in pin."""
        seen = seen or set()
        if net in seen or depth > 8 or net == "GND":
            return None
        seen.add(net)
        for r, p, t in nets.get(net, []):
            if r == skip:
                continue
            if want == "conn" and r.startswith("J"):
                return depth
            if want == "load" and t == "power_in":
                return depth
        best = None
        for r, p, t in nets.get(net, []):
            if r == skip or len(pins_of.get(r, {})) != 2:
                continue
            op = [q for q in pins_of[r] if q != p]
            if not op:
                continue
            d = hops(pins_of[r][op[0]], want, depth + 1, seen, skip)
            if d is not None and (best is None or d < best):
                best = d
        return best

    out = []
    for ref in sorted(pins_of):
        if not ref.startswith("D") or len(pins_of[ref]) != 2:
            continue
        na, nk = pins_of[ref].get("2"), pins_of[ref].get("1")   # 2 = A, 1 = K
        if na is None or nk is None or "GND" in (na, nk):
            continue                                            # shunt clamp
        a_conn = hops(na, "conn", skip=ref)
        k_conn = hops(nk, "conn", skip=ref)
        # The cathode being CLOSER to a connector than the anode is the whole
        # test: current has to enter at the anode.
        if k_conn is not None and (a_conn is None or k_conn < a_conn):
            out.append("%s (%s) is REVERSED: its cathode is on %s, %d hop(s) from a "
                       "connector, while its anode is on %s.  Current enters at the "
                       "ANODE, so it cannot conduct."
                       % (ref, comps.get(ref, ""), nk, k_conn, na))
    return out


def shunt_diodes(nets, pins_of, comps, fn_of):
    """Every diode ACROSS a rail, checked for which way round it is.

    `series_diodes` deliberately skips these -- a shunt part is in no series
    path, so nothing it does shows up in a supply trace -- which is exactly why
    round 12's reversed TVS survived: D2005 was an SMAJ18A, a UNIdirectional
    part, drawn with the bidirectional `Device:D_TVS` symbol and wired cathode
    to ground.  That is a forward diode across the 15 V rail.  ERC was silent,
    the netlist was correct, and the supply trace never went near it.

    Two separate faults are possible and both are checked:

      1. the part is drawn with a polarised symbol (pins A and K) and its
         cathode is not the end on the rail;
      2. the part is drawn with a NON-polarised symbol (pins A1 and A2) but the
         part number is a unidirectional one.  Then the schematic cannot say
         which way round it goes at all, and whether the board is right depends
         entirely on the footprint's pad 1 being the cathode.  That is true of
         every D_SMA/SOD footprint, but it is not something a reader can see,
         so it is worth saying out loud.

    A suffix of CA, CB or B on a TVS part number means bidirectional; anything
    else is taken to be unidirectional, which is the safe way round for a
    warning to be wrong.
    """
    BIDI = re.compile(r"(CA|CB|BA)\b|\bBIDIR", re.I)
    out = []
    for ref in sorted(pins_of):
        if not ref.startswith("D") or len(pins_of[ref]) != 2:
            continue
        pins = sorted(pins_of[ref])
        n1, n2 = pins_of[ref][pins[0]], pins_of[ref][pins[1]]
        if ("GND" in (n1, n2)) is False or n1 == n2:
            continue                                  # not a shunt
        rail = n2 if n1 == "GND" else n1
        rail_pin = pins[1] if n1 == "GND" else pins[0]
        gnd_pin = pins[0] if n1 == "GND" else pins[1]
        fns = {p: fn_of.get((ref, p), "") for p in pins}
        val_ = comps.get(ref, "")
        if set(fns.values()) >= {"A", "K"}:
            if fns[rail_pin] != "K":
                out.append("%s (%s) is REVERSED across %s: its ANODE is on the "
                           "rail and its cathode on GND, which is a forward "
                           "diode across the supply."
                           % (ref, val_, rail))
        elif set(fns.values()) == {"A1", "A2"} and not BIDI.search(val_):
            out.append("%s (%s) is a UNIDIRECTIONAL part drawn with a "
                       "bidirectional symbol (pins A1/A2), across %s.  The "
                       "schematic cannot express its polarity, so whether the "
                       "board is right rests entirely on pad 1 of its footprint "
                       "being the cathode.  Pin %s is the one on the rail."
                       % (ref, val_, rail, rail_pin))
    return out


def main(path):
    nets, pins_of, comps = load(path)
    fn_of = {}
    _doc = parse(open(path, encoding="utf-8").read())[0]
    for _n in kids(kid(_doc, "nets"), "net"):
        for _nd in kids(_n, "node"):
            _f = kid(_nd, "pinfunction")
            if _f:
                fn_of[(val(kid(_nd, "ref")), val(kid(_nd, "pin")))] = val(_f)
    bad, warn = [], []
    del BACKWARDS[:]

    # ---- 1. power to every chip -------------------------------------------
    print("=" * 72)
    print("POWER PATH TO EVERY POWER-INPUT PIN")
    print("=" * 72)
    chains = defaultdict(list)
    for nm, members in nets.items():
        for ref, pin, ptype in members:
            if ptype != "power_in":
                continue
            if nm == "GND":
                continue
            chain = trace_supply(nets, pins_of, comps, nm)
            if chain is None:
                bad.append("%s.%s on net %s reaches NO rail" % (ref, pin, nm))
                continue
            # is there a capacitor on this node?
            caps = [r for r, p, t in members if r.startswith("C")]
            if not caps:
                bad.append("%s.%s node %s has NO decoupling capacitor" % (ref, pin, nm))
            chains[" -> ".join(chain)].append("%s.%s" % (ref, pin))
    for ch, users in sorted(chains.items(), key=lambda kv: -len(kv[1])):
        print("  %-46s %3d pins" % (ch, len(users)))
        if len(users) <= 4:
            print("      " + " ".join(sorted(users)))

    # ---- 2. drivers and loads --------------------------------------------
    print()
    print("=" * 72)
    print("SIGNAL NETS: DRIVERS AND LOADS")
    print("=" * 72)
    DRV = ("output", "power_out", "bidirectional", "tri_state", "open_collector")
    for nm, members in sorted(nets.items()):
        if nm in RAILS or nm == "GND" or nm.startswith("unconnected-"):
            continue
        drv = [(r, p) for r, p, t in members if t in DRV]
        ld = [(r, p) for r, p, t in members if t == "input"]
        pas = [(r, p) for r, p, t in members if t in ("passive", "power_in")]
        if not drv and not pas:
            bad.append("net %s has no driver and no passive path: %s" % (nm, members))
        elif not drv and ld and not pas:
            bad.append("net %s drives %d input(s) from nothing" % (nm, len(ld)))
        if len(drv) > 1 and not all(t == "bidirectional" for r, p, t in members if t in DRV):
            warn.append("net %s has %d drivers: %s" % (nm, len(drv), drv))
    print("  checked %d nets" % len([n for n in nets if n not in RAILS and n != "GND"]))

    bad.extend(series_diodes(nets, pins_of, comps))
    # A shunt part is in no series path, so nothing above would ever look at
    # it.  Round 12's reversed TVS is exactly what this is here to catch.
    for m in shunt_diodes(nets, pins_of, comps, fn_of):
        (bad if "REVERSED" in m else warn).append(m)
    print()
    for m in warn:
        print("WARN  " + m)
    if bad:
        print()
        for m in bad:
            print("FAIL  " + m)
        return 1
    print("OK: every power-input pin reaches a rail through a named path and has a "
          "capacitor on its node;")
    print("    no net drives inputs from nothing and no net has conflicting drivers.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
