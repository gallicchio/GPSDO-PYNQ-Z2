#!/usr/bin/env python3
"""
JLCPCB CPL Rotation Fixer for GPSDO-PYNQ-Z2.

Problem:
KiCad footprint origins and zero-degree rotations for ICs and discrete semiconductors
often differ from the EIA-481 / IPC-7351 standard used by JLCPCB automated SMT pick-and-place
feeders. Specifically:
- SOT-23-5 and SOT-23-6: KiCad pin 1 is at (-1.14, -0.95) (top-left). In EIA-481 tape,
  pin 1 is oriented 180 deg opposite. Offset needed: +180 deg.
- SOT-223-3: Tab orientation in KiCad is top (+y). Tape feeder expects tab at bottom.
  Offset needed: +180 deg.
- SOIC-8: In KiCad, pin 1 is top-left. Standard tape pocket feed expects +270 deg or +90 deg.
- MSOP-10: Similar tape orientation offset (+270 deg or +90 deg).
- Diodes (SMA, SMB, SOD-323): KiCad pin 1 is Cathode. Depending on JLCPCB feeder, often 180 deg offset.

This script parses the BOM and original CPL, maps each part to its footprint family,
applies the required rotation offset, normalizes angles to [-180, 180], and emits
a JLCPCB-ready CPL.
"""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Rotation offsets (degrees to add to KiCad native rotation) for JLCPCB SMT
JLCPCB_ROTATION_OFFSETS = {
    "SOT-23-5": 180.0,
    "SOT-23-6": 180.0,
    "SOT-223-3_TabPin2": 180.0,
    "SOIC-8_3.9x4.9mm_P1.27mm": 270.0,
    "MSOP-10_3x3mm_P0.5mm": 270.0,
    "Oscillator_SMD_Fox_FT5H_5.0x3.2mm": 0.0,
    # Diodes: if Cathode is pin 1 in KiCad and tape expects Anode pin 1:
    "D_SMA": 180.0,
    "D_SMB": 180.0,
    "D_SOD-323": 180.0,
}


def norm_rot(r):
    r = float(r) % 360.0
    return r - 360.0 if r > 180.0 else r


def fix_cpl(bom_csv, cpl_csv, out_cpl_csv):
    # 1. Map designator -> Footprint from BOM
    ref_to_fp = {}
    with open(bom_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fp = row["Footprint"]
            refs = [r.strip() for r in row["Designator"].split(",") if r.strip()]
            for r in refs:
                ref_to_fp[r] = fp

    # 2. Read CPL and apply corrections
    corrected = []
    changes = []
    with open(cpl_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = row["Designator"]
            x = float(row["Mid X"])
            y = float(row["Mid Y"])
            layer = row["Layer"]
            orig_rot = float(row["Rotation"])
            fp = ref_to_fp.get(ref, "")

            offset = 0.0
            for fp_key, off in JLCPCB_ROTATION_OFFSETS.items():
                if fp_key in fp:
                    offset = off
                    break

            new_rot = norm_rot(orig_rot + offset)
            if abs(offset) > 1e-3:
                changes.append((ref, fp, orig_rot, new_rot, offset))

            corrected.append({
                "Designator": ref,
                "Mid X": "%.4f" % x,
                "Mid Y": "%.4f" % y,
                "Layer": layer,
                "Rotation": "%.4f" % new_rot
            })

    # 3. Write corrected CPL
    with open(out_cpl_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        writer.writeheader()
        writer.writerows(corrected)

    print("CPL Rotation Correction Summary:")
    print("  Total components in CPL: %d" % len(corrected))
    print("  Components adjusted: %d" % len(changes))
    print("\nSample adjustments:")
    for ref, fp, orig_rot, new_rot, off in changes[:10]:
        print("  %-6s  %-30s  Orig: %6.1f deg  ->  New: %6.1f deg  (offset: %+6.1f)"
              % (ref, fp, orig_rot, new_rot, off))
    print("Wrote corrected CPL to: %s" % out_cpl_csv)


if __name__ == "__main__":
    bom_path = os.path.join(ROOT, "mfg", "release", "GPSDO-PYNQ-Z2_bom.csv")
    cpl_path = os.path.join(ROOT, "mfg", "release", "GPSDO-PYNQ-Z2_cpl.csv")
    out_path = os.path.join(HERE, "GPSDO-PYNQ-Z2_cpl_jlcpcb.csv")
    fix_cpl(bom_path, cpl_path, out_path)
