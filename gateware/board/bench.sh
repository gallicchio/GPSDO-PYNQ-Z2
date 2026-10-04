#!/bin/bash
# The same automated battery before and after each rev A rework -- round 42.
#
#   ./bench.sh before     the board as it is now, just before a rework
#   ./bench.sh fb401      after bridging FB401
#   ./bench.sh xa         after R3001 3k3 -> 1k and R3002 1k -> 330R
#
# Cabling, the same at every stage: the Siglent on units 1 and 2 (one output,
# teed), the HP on unit 11, HO on unit 12 with its 50R jumper fitted.  Halfway
# through it asks you to move the Siglent's unit-1 cable to unit 4, and back.
#
# About 12 minutes.  Everything lands in logs/<stage>_<UTC time>/ and nothing
# is overwritten, so any two runs can be compared.  It re-programs the Si5351
# many times, so it refuses to start while another board script is running
# (the overnight si_watch.py, for one).
#
#   bringup.log            the whole bring-up, with the helper frequency
#   unplugged.log/.json    30 Si5351 restarts: which squarers oscillate
#   beats_std.log/.npz     30 s of units 1, 2, 11, 12 (crosstalk, scatter)
#   beats_u4.log/.npz      30 s of units 2, 4, 11, 12 (unit 4 driven)
#   matrix.log             CLK0 x CLK1 drive matrix, slips per second
#   summary.txt            the lines that matter from all of the above
set -u -o pipefail
cd "$(dirname "$0")"
stage=${1:-}
if ! [[ "$stage" =~ ^[a-z0-9_-]+$ ]]; then
    sed -n '2,22p' "$0"
    exit 2
fi
busy=$(pgrep -af 'python3 [^ ]*(si_watch|beats|unplugged|bringup)\.py')
if [ -n "$busy" ]; then
    echo "Another board script is running:"
    echo "$busy"
    echo "Stop it first, e.g.:  sudo pkill -f 'si_watch.py watch'"
    exit 1
fi
out=logs/${stage}_$(date -u +%Y%m%dT%H%MZ)
mkdir -p "$out"
touch "$out/.start"
echo "stage $stage -> $out"

run() {             # run NAME ARGS...: its output on screen and in NAME.log
    local name=$1
    shift
    echo
    echo "=== $name: $*"
    ./pynq-run "$@" 2>&1 | sed -u 's/^\[sudo\][^:]*: //' | tee "$out/$name.log"
}

keep() {            # keep NAME GLOB: move the file THIS run made into $out
    local f
    f=$(find . -maxdepth 1 -name "$2" -newer "$out/.start" -printf '%T@ %p\n' |
        sort -n | tail -1 | cut -d' ' -f2-)
    if [ -n "$f" ]; then
        mv "$f" "$out/$1"
    else
        echo "  (no new $2 to keep)"
    fi
}

run bringup bringup.py --inputs 1,2,11,12
run unplugged unplugged.py 30 1,2,11,12
keep unplugged.json 'unplugged_*.json'
run beats_std beats.py record 30 1 2 11 12
keep beats_std.npz 'beats_1_2_11_12_*.npz'
echo
read -r -p "Move the Siglent cable from unit 1 to unit 4, then press Enter " _
run beats_u4 beats.py record 30 2 4 11 12
keep beats_u4.npz 'beats_2_4_11_12_*.npz'
echo
read -r -p "Move it back from unit 4 to unit 1, then press Enter " _
run matrix si_watch.py matrix 8 2 12

{
    echo "stage $stage, $(date -u +%Y-%m-%dT%H:%MZ)"
    echo
    grep -E 'helper frequency|helper slips|latched flags|checks, [0-9]+ failures' "$out/bringup.log"
    echo
    sed -n '/^unit   quiet/,/^saved/p' "$out/unplugged.log" | grep -v '^saved'
    echo
    grep -h 'polls in' "$out/beats_std.log" "$out/beats_u4.log"
    echo
    python3 - "$out/matrix.log" <<'EOF'
import re, sys
rows = {}
for line in open(sys.argv[1]):
    m = re.match(r'CLK0 (\d) mA, CLK1 (\S+).*?PLLA (\d+) slips \(([\d.]+)/s\)', line)
    if m:
        rows.setdefault((m.group(1), m.group(2)), []).append(float(m.group(4)))
print('slips per second   CLK1:  2 mA        4 mA        6 mA        8 mA        off')
for c0 in '248':
    print('  CLK0 %s mA        ' % c0 + '  '.join(
        '%-10s' % '/'.join('%.0f' % r for r in rows.get((c0, c1), []))
        for c1 in ('2', '4', '6', '8', 'off')))
EOF
} > "$out/summary.txt"
echo
echo "=================== summary ($out/summary.txt)"
cat "$out/summary.txt"
