#!/usr/bin/env python3
"""Generate the whole GPSDO-PYNQ-Z2 KiCAD 9 schematic from design.py."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kigen, design as D
from kigen import Sch, uuid_for
import sheet_unit, sheets_rest

OUT = os.path.abspath(os.path.join(HERE, ".."))


BOARD_SHEETS = [("power.kicad_sch", "Power", "power",
                 "5 V entry, two low-noise LDOs, and the 12 V board heater"),
                ("helper.kicad_sch", "Helper", "helper",
                 "Si5351C + 25 MHz TCXO on CLKIN, HO buffered on its own bank, two LMK1C1108 fan-outs (rev B)"),
                ("header.kicad_sch", "RPi header", "rpi_header",
                 "the 2x20 socket, with every pin's Zynq site and function annotated"),
                ("housekeeping.kicad_sch", "Housekeeping", "housekeeping",
                 "8 x TMP1075 thermometers, the heater DAC, and the debug header"),
                ("probes.kicad_sch", "Probes", "probes",
                 "DS2482-100 bridge and five DS18B20 probe terminals")]


def board_sheets(root_uuid):
    out = []
    for fn, name, fnname, sub in BOARD_SHEETS:
        s = Sch(D.PROJECT, fn, paper="A2", rev=D.REV, company=D.COMPANY,
                title=name, comments=[sub])
        s.inst_path = "/%s/%s" % (root_uuid, uuid_for(D.PROJECT, "sheetbox", fn))
        getattr(sheets_rest, fnname)(s)
        s.finalize()
        out.append((s, name, fn))
    return out


def unit_sheets(root_uuid):
    out = []
    for u in D.UNITS:
        n = u[0]
        fn = "unit_%02d.kicad_sch" % n
        s = Sch(D.PROJECT, fn, paper="A2", rev=D.REV, company=D.COMPANY,
                title="Unit %d - %s" % (n, u[3]),
                comments=["10 MHz DDMTD channel + 1 pps channel" if u[2]
                          else "10 MHz DDMTD channel (NULL channel, no pps)"])
        # MUST be set before build(): sym() bakes the instance path into the
        # emitted text, so assigning it afterwards has no effect and KiCAD then
        # cannot resolve the symbol instances against the real hierarchy.
        s.inst_path = "/%s/%s" % (root_uuid, uuid_for(D.PROJECT, "sheetbox", fn))
        sheet_unit.build(s, u)
        s.finalize()
        out.append((s, "Unit %02d" % n, fn))
    return out


def root(children):
    s = Sch(D.PROJECT, D.PROJECT + ".kicad_sch", paper="A2", rev=D.REV,
            company=D.COMPANY, title="GPSDO front end for PYNQ-Z2 - index",
            comments=["13 x 10 MHz DDMTD + 12 x 1 pps into the Raspberry Pi header"])
    s.text(20.32, 25.4, "GPSDO-PYNQ-Z2   Digital DMTD front-end board", size=5.0, bold=True)
    s.text(20.32, 33.02,
           "13 x 10 MHz DDMTD channels (12 GPSDOs + 1 null) and 12 x 1 pps channels, "
           "into the PYNQ-Z2's 40-pin Raspberry Pi header.", size=2.0, italic=True)

    s.note(20.32, 40.64, 250.0, 62.0,
        "HOW THIS BOARD WORKS\n\n"
        "Each 10 MHz reference is terminated, AC-coupled and squared by a self-biased "
        "74LVC1GU04, then SAMPLED ON THIS BOARD by a flip-flop clocked from a helper at "
        "%.4f MHz.  The flip-flop output is a ~%.0f Hz beat whose edge times carry the input "
        "phase magnified by N = %.0f, so a %.1f ps input step becomes a full helper period at "
        "the FPGA.\n\n"
        "Sampling on this board rather than in the FPGA is the one architectural choice worth "
        "knowing: it keeps thirteen 10 MHz edges off a 2.54 mm header, and it means the FPGA's "
        "input threshold drift enters divided by N instead of at full scale."
        % (D.F_HELPER / 1e6, D.F_BEAT, D.N_GAIN, D.T_RES_PS), size=1.8)

    s.note(280.0, 40.64, 290.0, 62.0,
        "KEY NUMBERS\n\n"
        "f_signal   10.000000 MHz\n"
        "f_helper   %.7f MHz   (Si5351A CLK0, integer MultiSynth)\n"
        "f_beat     %.1f Hz\n"
        "N          %.0f      single-shot resolution %.1f ps\n"
        "tau_0      %.1f us per beat cycle\n\n"
        "The FPGA measures f_beat every epoch, so N is a count divided by a count and the "
        "helper's absolute frequency never enters the result."
        % (D.F_HELPER / 1e6, D.F_BEAT, D.N_GAIN, D.T_RES_PS, 1e6 / D.F_BEAT), size=1.8)

    # sheet boxes, laid out as a grid
    s.text(20.32, 118.0, "SHEETS", size=3.0, bold=True)
    x0, y0, w, h, dx, dy = 20.32, 124.0, 60.96, 22.86, 68.58, 33.02
    page = 2
    for i, (sch, name, fn) in enumerate(children):
        col, rowi = i % 8, i // 8
        s.sheet(x0 + col * dx, y0 + rowi * dy, w, h, name, fn, page)
        page += 1

    s.note(20.32, 250.0, 550.0, 40.0,
        "WHERE TO FIND A SIGNAL\n\n"
        "BEAT_00..BEAT_12   generated on the unit sheets, consumed on 'RPi header'.  "
        "~1234 Hz square, 0/3.3 V; the EDGE TIME is the measurement.\n"
        "PPS_00..PPS_11     generated on the unit sheets, consumed on 'RPi header'.  "
        "One rising edge per second.\n"
        "HELPER_FANOUT      generated on 'Helper', consumed on every unit sheet.  "
        "%.4f MHz, 3.3 V CMOS, edges ~1-2 ns.  Skew between branches enters the measurement "
        "1:1, so its tree is length-matched.\n"
        "HELPER_CLK         generated on 'Helper', consumed on 'RPi header' -> pin 18 "
        "(Y7, IO_L13P_T2_MRCC_13).\n"
        "I2C_SDA / I2C_SCL  header pins 3 and 5; Si5351, 8 x TMP1075, DS2482, MCP4725.  "
        "2k2 pull-ups are already fitted on the PYNQ-Z2.\n"
        "+3V3_A             front-end rail: every squarer, flip-flop, Schmitt and helper "
        "buffer.  One shared rail so threshold drift is common mode.\n"
        "+3V3_D             Si5351, TCXO and the I2C housekeeping parts only.\n"
        "+15V_HTR           heater only, from its own barrel jack; never touches the analog rails."
        % (D.F_HELPER / 1e6), size=1.8, color=(235, 240, 255))
    return s


def project_file(children):
    sheets = [[uuid_for(D.PROJECT, D.PROJECT + ".kicad_sch"), "Root"]]
    for sch, name, fn in children:
        sheets.append([uuid_for(D.PROJECT, "sheetbox", fn), name])
    import jlc
    return json.dumps({
        # ROUND 29.  Everything numeric here comes from gen/jlc.py, one row
        # per rule, each row asserting that our figure is at least as strict
        # as JLCPCB's published capability.  Before this the project set four
        # values -- clearance, track width, via size, via drill -- and left
        # KiCad's defaults to cover the other eleven, including the whole
        # silkscreen family; and it left every rule at its default SEVERITY,
        # which is how round 28 could report "0 violations" from a
        # --severity-error pass over a board with 639 warnings on it, 199 of
        # them reference designators printed below the minimum legible height
        # and 199 of them silkscreen landing on solder-mask openings.
        "board": {"design_settings": {"rules": jlc.rules(),
                                      "rule_severities": jlc.severities()}},
        "boards": [], "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": D.PROJECT + ".kicad_pro", "version": 3},
        "net_settings": {"meta": {"version": 3}, "net_colors": None,
                         "netclass_assignments": None, "netclass_patterns": [],
                         "classes": [
            # 0.15 mm, not KiCad's 0.2 default: the Si5351's MSOP-10 is 0.5 mm
            # pitch and its own pads sit 0.2 mm apart, so the default rule fails
            # on the part itself.  JLCPCB's standard capability is 0.127 mm.
            {"name": "Default", "clearance": 0.15, "track_width": 0.25,
             "via_diameter": 0.6, "via_drill": 0.3}]},
        "pcbnew": {"page_layout_descr_file": ""},
        # Every gate sits behind its own ferrite bead, so the node at its Vcc
        # pin is a DIFFERENT net from +3V3_A, with no power-output pin on it.
        # KiCad's convention is to stamp each such node with a PWR_FLAG; there
        # are 68 of them and 68 flags would bury the channel tiles.  The rails
        # themselves ARE driven (U2001.5 and U2002.5 are power outputs) and
        # gen/check_netlist.py verifies that independently, so the rule is
        # turned off here deliberately rather than left to be scrolled past.
        "erc": {"erc_exclusions": [], "meta": {"version": 0},
                "pin_map": [], "rule_severities": {"power_pin_not_driven": "ignore"},
                "rule_severity_overrides": []},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": sheets, "text_variables": {}}, indent=2)


def main():
    root_uuid = uuid_for(D.PROJECT, D.PROJECT + ".kicad_sch")
    children = board_sheets(root_uuid) + unit_sheets(root_uuid)
    r = root(children)
    si = ['\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)']
    r.save(OUT, sheet_instances=si[0])
    for sch, name, fn in children:
        sch.save(OUT, sheet_instances="")
    open(os.path.join(OUT, D.PROJECT + ".kicad_pro"), "w").write(project_file(children))
    import libs
    print("generated %d sheets in %s" % (len(children) + 1, OUT))
    print("wrote " + libs.write(OUT))


if __name__ == "__main__":
    main()
