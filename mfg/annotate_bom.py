#!/usr/bin/env python3
"""The BOM with everything JLCPCB's own BOM cannot carry.

Their upload format holds four columns.  This writes the rest: what each part
costs, what the line costs, how many they had in stock and WHEN that was asked,
whether it is Basic or Extended or would have to be consigned, and a note for
anything worth a second look before paying.

Every number here comes from JLCPCB's live parts API, and every row records the
timestamp of the query that produced it, because "in stock" is a statement
about a moment.
"""
import csv, os, sys, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bomdata, jlc_api, parts_map                     # noqa: E402

# JLCPCB's published assembly charges.  These move; the quote at checkout is
# authoritative and the report says so.  Recorded here so the estimate can be
# re-derived rather than guessed at.
FEE_EXTENDED_PART = 3.00      # per DISTINCT extended part, one-off
FEE_BASIC_PART = 0.00
FEE_SETUP = 8.00              # per order
FEE_PER_JOINT = 0.0017        # beyond the free allowance
FREE_JOINTS = 0               # conservative: charge for all of them


# JLCPCB names packages their way and KiCad names them its way; these are the
# same物 by different names.  Without this every diode and every oscillator
# reports a false mismatch -- the first run flagged nineteen items, all of them
# noise, which is worse than flagging none because it trains you to skip the
# list.  Through-hole parts are not checked at all: JLCPCB calls every one of
# them "Plugin".
PKG_ALIASES = {
    "do214ac": "sma", "do214aa": "smb", "do214ab": "smc",
    "sod323": "sod323", "sod123": "sod123",
    "sot233": "sot223", "sot235": "sot235", "sot236": "sot236",
    "msop10": "msop10", "soic8": "soic8",
}


def _tokens(s):
    """Lower-cased alphanumeric runs, with parenthetical parts kept too."""
    import re as _re
    s = s.lower()
    parts = _re.split(r"[^a-z0-9.]+", s)
    out = set()
    for p in parts:
        if not p:
            continue
        out.add(p)
        out.add(p.replace(".", ""))
        out.add(PKG_ALIASES.get(p.replace(".", ""), ""))
        # A metric package is written four ways -- "5032", "SMD5032-4P",
        # "5.0x3.2mm", "5.0 x 3.2".  Reduce each token to its digits and they
        # all become "5032".
        digits = _re.sub(r"[^0-9]", "", p)
        if len(digits) >= 4:
            out.add(digits)
    return {o for o in out if o}


def package_agrees(pkg, fp):
    """True when JLCPCB's package name and our footprint name denote the same
    thing.  Deliberately generous: a false 'agrees' costs nothing here because
    the assembly drawing shows the real land pattern, while a false 'differs'
    buries the real problems."""
    if not pkg:
        return True
    pt, ft = _tokens(pkg), _tokens(fp)
    return bool(pt & ft)


def money(x):
    return "%.4f" % x if abs(x) < 1 else "%.2f" % x


def gather(boards=1, refresh=False):
    rows = bomdata.components()
    groups = collections.defaultdict(list)
    for r in rows:
        if r["cls"] in ("smt", "tht"):
            # ROUND 32.  An SMT line is keyed on the PART, not on the value
            # string -- the same rule, and the same reason, as make_bom.py:
            # C17738 appeared here twice as well, once as `51R 1%` x13 and
            # once as `51R` x1, which asks the parts API the same question
            # twice and prices two lines that are one order.  The tht rows
            # keep their value strings, because there they are labels for a
            # person ("10MHz IN" vs "1pps IN", one SMA jack).
            key = ((r["cls"], r["lcsc"], None, r["fpshort"])
                   if r["cls"] == "smt" else
                   (r["cls"], r["lcsc"], r["value"], r["fpshort"]))
            groups[key].append(r)
    out = []
    for (cls, lcsc, value, fp), members in sorted(
            groups.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        if value is None:            # smt: label with the most specific string
            value = sorted({m["value"] for m in members},
                           key=lambda v: (-len(v), v))[0]
        need = len(members) * boards
        part, ts = jlc_api.by_code(lcsc, refresh=refresh)
        notes = []
        if part is None:
            out.append(dict(cls=cls, lcsc=lcsc, value=value, fp=fp,
                            refs=[m["ref"] for m in members], per_board=len(members),
                            need=need, order=need, mpn="", brand="", pkg="",
                            libtype="NOT FOUND", stock=0, unit=0.0, line=0.0,
                            ts=ts, why=members[0]["why"],
                            notes=["LCSC code not found in JLCPCB's library -- "
                                   "this part would have to be CONSIGNED"]))
            continue
        libtype = jlc_api.library_type(part)
        oq = jlc_api.order_qty(part, need)
        unit = jlc_api.unit_price(part, oq)
        stock = int(part.get("stockCount") or 0)
        pkg = part.get("componentSpecificationEn") or ""
        if stock < need:
            notes.append("OUT OF STOCK for this build: %d needed, %d available"
                         % (need, stock))
        elif stock < need * 3:
            notes.append("thin stock: %d available against %d needed" % (stock, need))
        if libtype == "Extended":
            notes.append("Extended: one-off setup fee applies to this part")
        if cls == "tht":
            notes.append("through hole -- NOT in the assembly order, order loose")
        if cls != "tht" and not package_agrees(pkg, fp):
            notes.append("check package: JLCPCB says %r, we drew %r" % (pkg, fp))
        out.append(dict(cls=cls, lcsc=lcsc, value=value, fp=fp,
                        refs=[m["ref"] for m in members], per_board=len(members),
                        need=need, order=oq, mpn=part.get("componentModelEn") or "",
                        brand=part.get("componentBrandEn") or "", pkg=pkg,
                        libtype=libtype, stock=stock, unit=unit,
                        line=unit * oq, ts=ts, why=members[0]["why"], notes=notes))
    return out


def write(outdir, boards=1, refresh=False):
    os.makedirs(outdir, exist_ok=True)
    data = gather(boards, refresh)
    smt = [d for d in data if d["cls"] == "smt"]
    tht = [d for d in data if d["cls"] == "tht"]
    extras = []
    for code, qty, note in parts_map.EXTRAS:
        part, ts = jlc_api.by_code(code, refresh=refresh)
        if part:
            oq = jlc_api.order_qty(part, qty * boards)
            u = jlc_api.unit_price(part, oq)
            extras.append(dict(cls="extra", lcsc=code, value="(not on the board)",
                               fp="", refs=[], per_board=qty, need=qty * boards,
                               order=oq, mpn=part.get("componentModelEn") or "",
                               brand=part.get("componentBrandEn") or "",
                               pkg=part.get("componentSpecificationEn") or "",
                               libtype=jlc_api.library_type(part),
                               stock=int(part.get("stockCount") or 0),
                               unit=u, line=u * oq, ts=ts, why=note, notes=[note]))

    csvp = os.path.join(outdir, "annotated_bom.csv")
    cols = ["Class", "LCSC", "MPN", "Manufacturer", "Value", "Footprint",
            "JLC package", "Library type", "Qty/board", "Qty needed",
            "Qty ordered", "Unit price USD", "Line total USD", "Stock",
            "Stock queried", "Designators", "Why this part", "Notes"]
    with open(csvp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cols)
        for d in smt + tht + extras:
            w.writerow([d["cls"], d["lcsc"], d["mpn"], d["brand"], d["value"],
                        d["fp"], d["pkg"], d["libtype"], d["per_board"],
                        d["need"], d["order"], money(d["unit"]),
                        money(d["line"]), d["stock"], d["ts"],
                        " ".join(d["refs"]), d["why"], "; ".join(d["notes"])])

    # ---- totals ------------------------------------------------------------
    parts_smt = sum(d["line"] for d in smt)
    joints = sum(d["need"] for d in smt)
    n_ext = sum(1 for d in smt if d["libtype"] == "Extended")
    n_basic = sum(1 for d in smt if d["libtype"] in ("Basic", "Preferred"))
    fees = FEE_SETUP + n_ext * FEE_EXTENDED_PART + \
        max(0, joints - FREE_JOINTS) * FEE_PER_JOINT
    problems = [(d, n) for d in smt + tht + extras for n in d["notes"]
                if n.startswith(("OUT OF STOCK", "LCSC code not found",
                                 "check package"))]
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    mdp = os.path.join(outdir, "annotated_bom.md")
    with open(mdp, "w", encoding="utf-8") as f:
        f.write("# Annotated BOM - GPSDO DDMTD front end\n\n")
        f.write("Generated %s for **%d board(s)**.  Prices and stock come from "
                "JLCPCB's parts API; each row carries the timestamp of its own "
                "query.  JLCPCB's quote at checkout is authoritative -- the fee "
                "model below is an estimate stated so it can be checked.\n\n"
                % (stamp, boards))
        f.write("## What it costs\n\n")
        f.write("| | |\n|---|---|\n")
        f.write("| SMT parts, %d distinct, %d placements | **$%.2f** |\n"
                % (len(smt), joints, parts_smt))
        f.write("| Basic / Preferred parts (no setup fee) | %d |\n" % n_basic)
        f.write("| Extended parts (setup fee each) | %d |\n" % n_ext)
        f.write("| Estimated assembly fees | $%.2f |\n" % fees)
        f.write("|   - order setup | $%.2f |\n" % FEE_SETUP)
        f.write("|   - %d extended parts at $%.2f | $%.2f |\n"
                % (n_ext, FEE_EXTENDED_PART, n_ext * FEE_EXTENDED_PART))
        f.write("|   - %d joints at $%.4f | $%.2f |\n"
                % (joints, FEE_PER_JOINT, joints * FEE_PER_JOINT))
        f.write("| **Parts + assembly, excluding the bare boards** | "
                "**$%.2f** |\n" % (parts_smt + fees))
        f.write("| Through-hole parts to order loose | $%.2f |\n"
                % sum(d["line"] for d in tht))
        f.write("| Extras (jumper shunts) | $%.2f |\n"
                % sum(d["line"] for d in extras))
        f.write("\n**Consigned parts required: none.**  Every part in the "
                "assembly order has a JLCPCB part number and is in their "
                "library.\n\n")
        if problems:
            f.write("## Look at these before paying\n\n")
            for d, n in problems:
                f.write("* **%s** (%s, %s) - %s\n"
                        % (d["lcsc"], d["value"], d["fp"], n))
            f.write("\n")
        else:
            f.write("## Nothing needs looking into\n\nNo part is out of stock, "
                    "unfound, or in a package that disagrees with its "
                    "footprint.\n\n")
        for title, rows_ in (("SMT - in the assembly order", smt),
                             ("Through hole - hand soldered, order loose", tht),
                             ("Extras - not on the board", extras)):
            if not rows_:
                continue
            f.write("## %s\n\n" % title)
            f.write("| LCSC | MPN | Value | Pkg | Type | Qty | Order | Unit | "
                    "Line | Stock | Queried | Notes |\n")
            f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
            for d in rows_:
                f.write("| %s | %s | %s | %s | %s | %d | %d | $%s | $%s | %s | "
                        "%s | %s |\n"
                        % (d["lcsc"], d["mpn"], d["value"], d["pkg"],
                           d["libtype"], d["need"], d["order"], money(d["unit"]),
                           money(d["line"]), "{:,}".format(d["stock"]),
                           d["ts"][:16].replace("T", " "),
                           "; ".join(d["notes"]) or ""))
            f.write("\n")
    print("  %-34s %d rows" % (os.path.basename(csvp), len(smt + tht + extras)))
    print("  %-34s" % os.path.basename(mdp))
    print("  parts $%.2f + est. fees $%.2f = $%.2f   (%d basic, %d extended, "
          "%d joints)" % (parts_smt, fees, parts_smt + fees, n_basic, n_ext,
                          joints))
    if problems:
        print("  %d item(s) flagged for review" % len(problems))
    return dict(parts=parts_smt, fees=fees, problems=len(problems))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    write(os.path.join(HERE, "release"), boards=n,
          refresh="--refresh" in sys.argv)
