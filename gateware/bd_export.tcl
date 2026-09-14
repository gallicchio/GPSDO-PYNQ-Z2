# ---------------------------------------------------------------------------
# Export Vivado's OWN block-diagram drawing, as PDF and SVG.
#
#     vivado -mode gui -source gateware/bd_export.tcl
#
# GUI MODE IS REQUIRED and that is not a preference.  write_bd_layout is
# implemented by the block-design canvas widget, so with -mode batch it prints
#
#     WARNING: [BD 5-349] write_bd_layout failed. Please run the tool in
#     GUI mode and try again.
#
# ...and then RETURNS SUCCESS having written nothing.  It is a warning, not an
# error, so a `catch` around it does not fire and a script that trusts the
# return value will happily report a file it never created.  Check for the
# file, which is what this script does at the end.
#
# The batch build (build.tcl) therefore draws its own Graphviz diagram instead,
# which is a schematic of the same design rather than Vivado's rendering.  Run
# this when you want the real thing.  It needs $DISPLAY.
# ---------------------------------------------------------------------------

set script_dir [file normalize [file dirname [info script]]]
set build_dir  $script_dir/build

set proj $build_dir/dmtd/dmtd.xpr
if {[llength $argv] > 0} { set proj [lindex $argv 0] }
if {![file exists $proj]} {
    error "no project at $proj -- run build.tcl first"
}

set stem [file rootname [file tail $proj]]
open_project $proj
open_bd_design [get_files dmtd_top.bd]

# Vivado places the blocks; a block design built entirely by script carries no
# geometry until something lays it out.
regenerate_bd_layout
save_bd_design

set wrote {}
foreach fmt {pdf svg} {
    set out $build_dir/${stem}_bd_layout.$fmt
    file delete -force $out
    write_bd_layout -force -format $fmt -orientation portrait $out
    if {[file exists $out]} {
        lappend wrote $out
    } else {
        puts "*** write_bd_layout produced no $fmt -- is this really GUI mode?"
    }
}

puts "\n=== block diagram exported ==="
foreach f $wrote { puts "    $f  ([file size $f] bytes)" }
if {![llength $wrote]} { error "write_bd_layout wrote nothing" }
exit 0
