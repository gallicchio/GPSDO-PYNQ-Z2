# ---------------------------------------------------------------------------
# Talk to the measurement core over JTAG, with no PS, no SD card, no network
# and nothing plugged into the front-end header:
#
#     vivado -mode batch -source gateware/bringup.tcl
#     vivado -mode batch -source gateware/bringup.tcl -tclargs -bit some.bit
#
# This programs a -bench or -plclk bitstream and drives its jtag_axi master
# from the hardware manager.  It is the first thing to run on a new board: it
# separates "the gateware is wrong" from "the board is not powered the way I
# think it is", which are otherwise indistinguishable from a dead console.
#
# With nothing connected, the helper clock is absent, so the checks that
# matter are the ones that do not need it: identity, the address map, and the
# write path.  ALIVE reading 0 is a PASS here -- it means the helper watchdog
# works.
# ---------------------------------------------------------------------------

set script_dir [file normalize [file dirname [info script]]]
set bit  $script_dir/build/bench_plclk/dmtd_top.bit
set base 43C00000
set iic  41600000

for {set i 0} {$i < [llength $argv]} {incr i} {
    switch -- [lindex $argv $i] {
        -bit  { incr i; set bit  [lindex $argv $i] }
        -base { incr i; set base [lindex $argv $i] }
    }
}
if {![file exists $bit]} {
    error "no bitstream at $bit -- build one with: vivado -mode batch -source gateware/build.tcl -tclargs -plclk"
}

set ::checks 0
set ::fails  0
proc note {ok name detail} {
    incr ::checks
    if {$ok} {
        puts [format "ok    %-46s %s" $name $detail]
    } else {
        incr ::fails
        puts [format "FAIL  %-46s %s" $name $detail]
    }
}

# ---------------------------------------------------------------------------
open_hw_manager
connect_hw_server -quiet
open_hw_target
current_hw_device [lindex [get_hw_devices xc7z020_1] 0]
set_property PROGRAM.FILE $bit [current_hw_device]
puts "--- programming [file tail $bit]"
program_hw_devices [current_hw_device]
refresh_hw_device -update_hw_probes false [current_hw_device]

set axis [get_hw_axis -quiet]
if {![llength $axis]} {
    puts "\n*** no JTAG-AXI master was found in the programmed device."
    puts "*** The bitstream contains one, so its debug hub is not answering,"
    puts "*** which means its clock is not running.  If this was the -bench"
    puts "*** build, the AXI fabric is clocked by the PS's FCLK_CLK0 -- and"
    puts "*** FCLK_CLK0 only runs once something has configured the PS (an"
    puts "*** FSBL from the SD card, or ps7_init over JTAG).  Rebuild with"
    puts "*** -plclk to clock the fabric from the board's own 125 MHz"
    puts "*** oscillator instead, which needs nothing from the PS."
    error "no debug core in the device"
}
set jt [lindex $axis 0]
puts "--- JTAG-AXI master: $jt"

proc axi_rd {addr} {
    global jt
    catch {delete_hw_axi_txn [get_hw_axi_txns -quiet t_rd]}
    create_hw_axi_txn t_rd $jt -address $addr -type read -len 1
    run_hw_axi -quiet t_rd
    return [get_property DATA [get_hw_axi_txns t_rd]]
}
proc axi_wr {addr data} {
    global jt
    catch {delete_hw_axi_txn [get_hw_axi_txns -quiet t_wr]}
    create_hw_axi_txn t_wr $jt -address $addr -type write -len 1 -data $data
    run_hw_axi -quiet t_wr
}
proc off {base n} { return [format %08X [expr {"0x$base" + $n}]] }

# ---- identity -------------------------------------------------------------
puts "\n=== identity ==="
set id [axi_rd [off $base 0x000]]
note [expr {$id eq "444d5444"}] "ID reads DMTD" "0x$id"
if {$id ne "444d5444"} { error "wrong bitstream in the device" }
set ver [axi_rd [off $base 0x004]]
note [expr {$ver eq "01000d0c"}] "VERSION v1.0, 13 beats, 12 pps" "0x$ver"

# ---- the write path -------------------------------------------------------
# CONTROL reads back the toggle bit that the write actually drives, so this
# tests the write decode end to end on silicon.  It is worth doing explicitly:
# this decode was broken, and because BRESP was still OKAY nothing complained
# -- writes simply went to the address of the write before them, so the FIRST
# write of a session was always lost.
puts "\n=== the write path (CONTROL bit 0 -> the clear toggle) ==="
set t0 [axi_rd [off $base 0x008]]
axi_wr [off $base 0x008] 00000001
set t1 [axi_rd [off $base 0x008]]
note [expr {$t0 ne $t1}] "the FIRST CONTROL write is not dropped" "$t0 -> $t1"
axi_wr [off $base 0x008] 00000001
set t2 [axi_rd [off $base 0x008]]
note [expr {$t1 ne $t2}] "a second CONTROL write toggles again" "$t1 -> $t2"
axi_wr [off $base 0x008] 00000000
set t3 [axi_rd [off $base 0x008]]
note [expr {$t2 eq $t3}] "CONTROL with bit0=0 does nothing" "$t2 -> $t3"
axi_wr [off $base 0x000] FFFFFFFF
set t4 [axi_rd [off $base 0x008]]
note [expr {$t3 eq $t4}] "a write to 0x000 does not reach CONTROL" "$t3 -> $t4"

# ---- the helper, which is absent with nothing plugged in ------------------
puts "\n=== helper clock ==="
set alive  [axi_rd [off $base 0x018]]
set hz     [axi_rd [off $base 0x00C]]
set live   [axi_rd [off $base 0x010]]
note [expr {$alive eq "00000000"}] "ALIVE is 0 with no front-end board" "0x$alive"
note [expr {$hz    eq "00000000"}] "HELPER is 0 with no helper clock"   "0x$hz"
note [expr {$live  eq "00000000"}] "the helper counter never advanced"  "0x$live"

# ---- the address map ------------------------------------------------------
puts "\n=== address map ==="
set nonzero {}
for {set n 0} {$n < 13} {incr n} {
    set c [axi_rd [off $base [expr {0x200 + 16*$n + 8}]]]
    if {$c ne "00000000"} { lappend nonzero "beat$n=0x$c" }
}
for {set n 16} {$n < 28} {incr n} {
    set c [axi_rd [off $base [expr {0x200 + 16*$n + 8}]]]
    if {$c ne "00000000"} { lappend nonzero "pps[expr {$n-16}]=0x$c" }
}
note [expr {![llength $nonzero]}] "all 25 channels read 0 with no inputs" $nonzero
set resv [axi_rd [off $base 0x20C]]
note [expr {$resv eq "00000000"}] "reserved channel word reads 0" "0x$resv"
set unmapped [axi_rd [off $base 0x0FC]]
note [expr {$unmapped eq "00000000"}] "unmapped register reads 0" "0x$unmapped"

# ---- the second slave on the interconnect ---------------------------------
puts "\n=== axi_iic at 0x$iic ==="
set sr [axi_rd [off $iic 0x104]]
note [expr {$sr ne "00000000" && $sr ne "ffffffff"}] \
     "IIC status register answers" "0x$sr (PG090 reset value is 0xC0)"

# ---------------------------------------------------------------------------
puts "\n=== $::checks checks, $::fails failures ==="
close_hw_manager
if {$::fails} { error "bring-up failed" }
puts "=== BRING-UP PASS ==="
exit 0
