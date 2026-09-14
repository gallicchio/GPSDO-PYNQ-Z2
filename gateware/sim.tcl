# ---------------------------------------------------------------------------
# Run the self-checking testbench for the measurement core:
#
#     vivado -mode batch -source gateware/sim.tcl
#
# Exits non-zero unless the testbench prints TB PASS, so it can gate a build.
# Nothing here touches the overlay project; it builds its own throwaway one
# under build/sim/ from the same RTL the bitstream is made from.
# ---------------------------------------------------------------------------

set script_dir [file normalize [file dirname [info script]]]
set build_dir  $script_dir/build
set sim_dir    $build_dir/sim

file mkdir $build_dir
if {[file exists $sim_dir]} { file delete -force $sim_dir }

create_project sim $sim_dir -part xc7z020clg400-1 -force
set_property target_language Verilog [current_project]

add_files -norecurse [glob $script_dir/rtl/*.v]
add_files -fileset sim_1 -norecurse [glob $script_dir/sim/*.v]
set_property top tb_dmtd_capture [get_filesets sim_1]
set_property top_lib xil_defaultlib [get_filesets sim_1]
set_property -name {xsim.simulate.runtime} -value {all} -objects [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

launch_simulation
close_sim

set log $sim_dir/sim.sim/sim_1/behav/xsim/simulate.log
if {![file exists $log]} { error "no simulation log at $log" }
set fh [open $log r]
set txt [read $fh]
close $fh

puts "\n=== testbench output ==="
foreach line [split $txt "\n"] {
    if {[regexp {^(ok|FAIL|===|      )} $line]} { puts $line }
}

if {[string first "TB PASS" $txt] < 0} {
    puts "\n*** TESTBENCH FAILED -- full log: $log"
    error "testbench failed"
}
puts "\n=== TB PASS ==="
exit 0
