#!/bin/bash
# The night after a set of rev A reworks -- round 45.  Runs on the LAPTOP:
#
#   ./night.sh STAGE [HOURS]          e.g.  ./night.sh mods 13
#
# 1. bench.sh STAGE on the PYNQ (round 42's battery), with unit 4 undriven:
#    the 33220A is switched off for it and on again after.  Compare with
#    logs/before_20261006T2325Z.
# 2. toggle_test.py 8: unit 4 driven <-> oscillating, and the step it puts on
#    unit 2 - unit 1 (+1.9 ps before any rework).
# 3. overnight.py for HOURS with the board heater stepped: off 1 h, on 3 h,
#    off 3 h, on 3 h, then off.  The heater heats the board, not the SDG,
#    so the pairs' drift during a step is the board's own.
#
# PYNQ_SSH / PYNQ_SCP as for xcheck.py.  Each step's output goes to the
# console; the data to bench.sh's logs/ on the PYNQ, toggle_<UTC>/ and
# overnight_<UTC>/ here.
set -u
cd "$(dirname "$0")"
stage=${1:?usage: ./night.sh STAGE [HOURS]}
hours=${2:-13}
SSH=${PYNQ_SSH:-ssh xilinx@192.168.8.156}
echo "=== $(date -u +%FT%TZ)  bench.sh $stage (unit 4 undriven)"
python3 bench_setup.py unit4 off
$SSH "cd ~/gpsdo-dmtd && ./bench.sh $stage"
python3 bench_setup.py unit4 on
echo "=== $(date -u +%FT%TZ)  toggle_test.py 8"
python3 toggle_test.py 8
echo "=== $(date -u +%FT%TZ)  overnight.py $hours h, heater stepped"
python3 overnight.py "$hours" --period 120 --heater 0:off,60:on,240:off,420:on,600:off
echo "=== $(date -u +%FT%TZ)  done"
