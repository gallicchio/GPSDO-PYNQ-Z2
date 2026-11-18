# ---------------------------------------------------------------------------
# Build the GPSDO DDMTD overlay for a PYNQ-Z2, from nothing, in one command:
#
#     vivado -mode batch -source gateware/build.tcl
#
# Everything is scripted -- the project, the block design, the connections, the
# address map, synthesis, implementation and the handoff files -- so the result
# is reproducible and reviewable as a diff rather than as a screenshot.  The
# block design is still a real IP Integrator design: open it with
#     vivado gateware/build/dmtd/dmtd.xpr
# and it draws the diagram.
#
# Board files are vendored under gateware/board_files/ so this does not need
# the network or a Vivado board-file install.
#
# Options (pass with -tclargs):
#     -synth_only     stop after synthesis, do not implement
#     -jobs N         parallel jobs (default 8)
#     -bench          build the bring-up variant instead: identical, plus a
#                     JTAG-to-AXI master so the register map can be read and
#                     written from Vivado's hardware manager over the same USB
#                     cable, with no PS, no SD card and no host on the network.
#                     Writes to build/bench/, never to build/overlay/.
#     -plclk          implies -bench, and additionally clocks the whole AXI
#                     fabric from H16 (via an MMCM to 100 MHz) with a constant
#                     reset, so that NOTHING in the PL depends on the PS having
#                     been configured.  This is the variant to use on a board
#                     whose PS has not booted: with no FSBL, FCLK_CLK0 does not
#                     run and FCLK_RESET0_N stays low, so the ordinary -bench
#                     build cannot even be talked to -- its debug hub has no
#                     clock.
#
#                     PLUG IN AN ETHERNET CABLE before using -plclk.  H16 is
#                     not an oscillator: it is the Ethernet PHY's CLK125 (see
#                     xdc/bench_plclk.xdc), and with no cable the PHY can stop
#                     and restart it about once a second.
# ---------------------------------------------------------------------------

set script_dir [file normalize [file dirname [info script]]]
set proj_root  [file dirname $script_dir]
set build_dir  $script_dir/build
set proj_name  dmtd
set bd_name    dmtd_top

set synth_only 0
set bench      0
set plclk      0
set jobs       8
for {set i 0} {$i < [llength $argv]} {incr i} {
    switch -- [lindex $argv $i] {
        -synth_only { set synth_only 1 }
        -bench      { set bench 1 }
        -plclk      { set bench 1; set plclk 1 }
        -jobs       { incr i; set jobs [lindex $argv $i] }
    }
}
if {$plclk} { set proj_name dmtd_bench_plclk } elseif {$bench} { set proj_name dmtd_bench }

puts "=== GPSDO DDMTD overlay ==="
puts "    project root : $proj_root"
puts "    build dir    : $build_dir"

# ---------------------------------------------------------------------------
# 1. constraints are generated from the board's own source of truth
# ---------------------------------------------------------------------------
set xdc $script_dir/xdc/pins.xdc
puts "--- regenerating $xdc from gen/design.py"
if {[catch {exec python3 $script_dir/gen_xdc.py $xdc} msg]} {
    puts "WARNING: could not regenerate the XDC ($msg); using the checked-in one"
}
if {![file exists $xdc]} { error "no constraints file at $xdc" }

# ---------------------------------------------------------------------------
# 2. project
# ---------------------------------------------------------------------------
file mkdir $build_dir
if {[file exists $build_dir/$proj_name]} { file delete -force $build_dir/$proj_name }
create_project $proj_name $build_dir/$proj_name -part xc7z020clg400-1 -force
set_property board_part_repo_paths [list $script_dir/board_files] [current_project]
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
set_property target_language Verilog [current_project]

add_files -norecurse [glob $script_dir/rtl/*.v]
add_files -fileset constrs_1 -norecurse $xdc
if {$plclk} { add_files -fileset constrs_1 -norecurse $script_dir/xdc/bench_plclk.xdc }
update_compile_order -fileset sources_1

# ---------------------------------------------------------------------------
# 3. block design
# ---------------------------------------------------------------------------
create_bd_design $bd_name
current_bd_design $bd_name

# ---- the Zynq PS, configured from the PYNQ-Z2 board preset ----------------
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" \
             Master "Disable" Slave "Disable"} $ps

# One 100 MHz PL clock and one general-purpose AXI master is all this needs.
set_property -dict [list \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_EN_CLK0_PORT {1} \
] $ps

# ---- reset and interconnect ----------------------------------------------
set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_ps7_100M]
set sc  [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect axi_sc]
set_property -dict [list CONFIG.NUM_SI [expr {$bench ? 2 : 1}] CONFIG.NUM_MI {2}] $sc

# ---- bring-up only: a second AXI master driven straight from JTAG ----------
# The PS is the only master in the delivered overlay.  For bring-up that is a
# problem: it means every register read depends on Linux being up, on the
# console being reachable, and on the board having a network.  A jtag_axi gives
# a second, entirely independent way in over the same USB cable that programs
# the part, so the measurement core can be exercised on real silicon before any
# of that works.  It is never in the delivered overlay -- an unauthenticated
# AXI master reachable over JTAG is a debug tool, not a feature.
if {$bench} {
    set jax [create_bd_cell -type ip -vlnv xilinx.com:ip:jtag_axi jtag_axi_0]
    set_property -dict [list CONFIG.PROTOCOL {2}] $jax
}

# ---- the measurement core, as a module reference --------------------------
# A plain RTL module rather than a packaged IP: one file, no IP repository, and
# IP Integrator infers the AXI4-Lite interface from the X_INTERFACE attributes
# in the Verilog.
set cap [create_bd_cell -type module -reference dmtd_capture dmtd_capture_0]

# ---- I2C to the Si5351, the eight thermometers, the DAC and the 1-Wire -----
# The PYNQ already fits 2k2 pull-ups on these two header pins (R305-R308), so
# the front-end board fits none.
set iic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_iic axi_iic_0]
set_property -dict [list CONFIG.IIC_FREQ_KHZ {100}] $iic

# ---- clocks and resets ----------------------------------------------------
# Normally both come from the PS: FCLK_CLK0 and FCLK_RESET0_N.  In the -plclk
# bring-up variant they come from the board's 125 MHz oscillator and a tied
# constant instead, because on a board whose PS has not been configured
# FCLK_CLK0 does not toggle and FCLK_RESET0_N sits low -- the fabric would be
# stopped and held in reset, and even the debug hub would be unclocked.
if {$plclk} {
    # H16 is the Ethernet PHY's CLK125, not an oscillator -- see
    # xdc/bench_plclk.xdc.  Keep a cable in the jack while using this variant.
    create_bd_port -dir I -type clk -freq_hz 125000000 sys_clk
    # Through an MMCM to 100 MHz, not straight in at 125.  Two reasons: the
    # design is built for a 10 ns period and closes with ~1.3 ns to spare, so
    # 8 ns does not fit (the first attempt came back at WNS -2.731 ns and the
    # timing guard refused it); and running the bring-up variant at the same
    # frequency as the delivered overlay means it exercises the same timing
    # closure rather than a different one.
    set mmcm [create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz clk_wiz_0]
    set_property -dict [list \
        CONFIG.PRIM_IN_FREQ {125.000} \
        CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000} \
        CONFIG.USE_LOCKED {true} \
        CONFIG.USE_RESET {false} \
    ] $mmcm
    connect_bd_net [get_bd_ports sys_clk] [get_bd_pins clk_wiz_0/clk_in1]
    set axi_clk [get_bd_pins clk_wiz_0/clk_out1]
    set one [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant const_1]
    set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] $one
    set_property -dict [list CONFIG.C_EXT_RESET_HIGH {0}] $rst
    set axi_rst_src [get_bd_pins const_1/dout]
} else {
    set axi_clk     [get_bd_pins ps7/FCLK_CLK0]
    set axi_rst_src [get_bd_pins ps7/FCLK_RESET0_N]
}
connect_bd_net $axi_clk \
               [get_bd_pins rst_ps7_100M/slowest_sync_clk] \
               [get_bd_pins ps7/M_AXI_GP0_ACLK] \
               [get_bd_pins axi_sc/aclk] \
               [get_bd_pins dmtd_capture_0/s_axi_aclk] \
               [get_bd_pins axi_iic_0/s_axi_aclk]
if {$bench} {
    connect_bd_net $axi_clk [get_bd_pins jtag_axi_0/aclk]
}
connect_bd_net $axi_rst_src [get_bd_pins rst_ps7_100M/ext_reset_in]
if {$plclk} {
    connect_bd_net [get_bd_pins clk_wiz_0/locked] [get_bd_pins rst_ps7_100M/dcm_locked]
}
connect_bd_net [get_bd_pins rst_ps7_100M/peripheral_aresetn] \
               [get_bd_pins axi_sc/aresetn] \
               [get_bd_pins dmtd_capture_0/s_axi_aresetn] \
               [get_bd_pins axi_iic_0/s_axi_aresetn]

# ---- AXI ------------------------------------------------------------------
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins axi_sc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_sc/M00_AXI] [get_bd_intf_pins dmtd_capture_0/S_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_sc/M01_AXI] [get_bd_intf_pins axi_iic_0/S_AXI]
if {$bench} {
    connect_bd_net [get_bd_pins rst_ps7_100M/peripheral_aresetn] \
                   [get_bd_pins jtag_axi_0/aresetn]
    connect_bd_intf_net [get_bd_intf_pins jtag_axi_0/M_AXI] \
                        [get_bd_intf_pins axi_sc/S01_AXI]
}

# ---- the pins that go to the front-end board ------------------------------
create_bd_port -dir I -type clk -freq_hz 10001234 helper_clk
connect_bd_net [get_bd_ports helper_clk] [get_bd_pins dmtd_capture_0/helper_clk]
create_bd_port -dir I -from 12 -to 0 beat
connect_bd_net [get_bd_ports beat] [get_bd_pins dmtd_capture_0/beat]
create_bd_port -dir I -from 11 -to 0 pps
connect_bd_net [get_bd_ports pps] [get_bd_pins dmtd_capture_0/pps]
make_bd_intf_pins_external -name iic [get_bd_intf_pins axi_iic_0/IIC]

# ---- address map ----------------------------------------------------------
assign_bd_address
set_property offset 0x43C00000 [get_bd_addr_segs {ps7/Data/SEG_dmtd_capture_0_reg0}]
set_property range  4K         [get_bd_addr_segs {ps7/Data/SEG_dmtd_capture_0_reg0}]
if {$bench} {
    # the JTAG master sees the same addresses the PS does, so a bring-up script
    # and a PYNQ driver can use one register map
    set_property offset 0x43C00000 [get_bd_addr_segs {jtag_axi_0/Data/SEG_dmtd_capture_0_reg0}]
    set_property range  4K         [get_bd_addr_segs {jtag_axi_0/Data/SEG_dmtd_capture_0_reg0}]
}

validate_bd_design
save_bd_design

# ---- the block diagram, three ways ----------------------------------------
# write_bd_layout needs a GUI and this runs headless, so the diagram is
# produced from the design itself rather than from a screenshot: a Graphviz
# graph walked out of the BD's own cells and interface nets.  It is generated,
# so it cannot drift from the design the way an exported image does.
#
# write_bd_tcl is the canonical Vivado way to carry a block design in version
# control -- it regenerates the diagram exactly.
set tag [expr {$plclk ? "bench_plclk_" : ($bench ? "bench_" : "")}]
write_bd_tcl -force $build_dir/${tag}${bd_name}_bd.tcl

source $script_dir/bd_diagram.tcl
bd_diagram $build_dir/${tag}${bd_name}.dot \
           $build_dir/${tag}${bd_name}_block_diagram.pdf \
           "GPSDO DDMTD overlay - $bd_name"

# ---------------------------------------------------------------------------
# 4. wrapper, synthesis, implementation
# ---------------------------------------------------------------------------
set bd_file [get_files $bd_name.bd]
make_wrapper -files $bd_file -top
# Vivado 2022.x puts the wrapper under .gen, older versions under .srcs.
set wrapper ""
foreach cand [list \
      $build_dir/$proj_name/${proj_name}.gen/sources_1/bd/$bd_name/hdl/${bd_name}_wrapper.v \
      $build_dir/$proj_name/${proj_name}.srcs/sources_1/bd/$bd_name/hdl/${bd_name}_wrapper.v] {
    if {[file exists $cand]} { set wrapper $cand; break }
}
if {$wrapper eq ""} { error "cannot find the generated BD wrapper" }
add_files -norecurse $wrapper
set_property top ${bd_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {
    error "SYNTHESIS FAILED -- see $build_dir/$proj_name/${proj_name}.runs/synth_1"
}
puts "--- synthesis complete"

if {$synth_only} { puts "--- -synth_only given, stopping"; exit 0 }

launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {
    error "IMPLEMENTATION FAILED -- see $build_dir/$proj_name/${proj_name}.runs/impl_1"
}

# ---------------------------------------------------------------------------
# 5. timing, and the handoff files PYNQ actually loads
# ---------------------------------------------------------------------------
open_run impl_1
set wns [get_property SLACK [get_timing_paths -delay_type max]]
set whs [get_property SLACK [get_timing_paths -delay_type min]]
puts "--- TIMING: WNS = $wns ns   WHS = $whs ns"
set tag [expr {$plclk ? "bench_plclk_" : ($bench ? "bench_" : "")}]
report_utilization -file $build_dir/${tag}utilization.rpt
report_timing_summary -file $build_dir/${tag}timing_summary.rpt

# A bitstream that fails timing is not a result, it is a trap: it will load,
# it will mostly work, and it will be wrong occasionally and unrepeatably.
# The first build of this design closed with WNS = -4.275 ns and still wrote a
# .bit, which is exactly the failure mode this check exists to prevent.
if {$wns < 0 || $whs < 0} {
    puts "\n*** TIMING NOT MET: WNS = $wns ns, WHS = $whs ns"
    puts "*** see $build_dir/timing_summary.rpt"
    error "timing not met -- refusing to publish the overlay"
}

# PYNQ wants <name>.bit and <name>.hwh side by side, with the same stem.
set bit [glob -nocomplain $build_dir/$proj_name/${proj_name}.runs/impl_1/*.bit]
set hwh [glob -nocomplain $build_dir/$proj_name/${proj_name}.gen/sources_1/bd/$bd_name/hw_handoff/$bd_name.hwh]
if {$hwh eq ""} {
    set hwh [glob -nocomplain $build_dir/$proj_name/${proj_name}.srcs/sources_1/bd/$bd_name/hw_handoff/$bd_name.hwh]
}
set out [expr {$plclk ? "$build_dir/bench_plclk" : ($bench ? "$build_dir/bench" : "$build_dir/overlay")}]
file mkdir $out
if {$bit ne ""} { file copy -force [lindex $bit 0] $out/$bd_name.bit }
if {$hwh ne ""} { file copy -force [lindex $hwh 0] $out/$bd_name.hwh }

if {!$bench} {
    # ps7_init, so the board can be brought up over JTAG with no SD card
    write_hw_platform -fixed -include_bit -force $out/$bd_name.xsa
}

# Vivado's PS7 board-preset automation drops a summary into a directory named
# from an unset variable, next to wherever it was launched.  Remove it rather
# than leave a folder called "NA" in a repository other people will check out.
if {[file isdirectory $script_dir/NA]} { file delete -force $script_dir/NA }

puts "\n=== DONE ==="
puts "    [expr {$bench ? {bench   } : {overlay }}]: $out/$bd_name.bit  +  .hwh"
if {$plclk} { puts "    AXI fabric clocked from H16 (125 MHz), reset tied -- PS not required" }
puts "    diagram : $build_dir/${tag}${bd_name}_block_diagram.pdf"
puts "    timing  : WNS $wns ns, WHS $whs ns"
exit 0
