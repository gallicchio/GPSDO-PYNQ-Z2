# ---------------------------------------------------------------------------
# Draw the block design, in batch.
#
# Vivado's own write_bd_layout needs a GUI, and this project builds headless,
# so the diagram is walked out of the design itself with Graphviz.  That is
# better than an exported screenshot in one respect that matters here: it is
# generated from the BD every build, so it cannot drift from the design.
#
# Sourced by build.tcl, or standalone against an existing project:
#     vivado -mode batch -source gateware/bd_diagram.tcl -tclargs <proj.xpr> <bd>
#
# The Zynq PS drags 25 DDR_* and FIXED_IO_* external ports into any block
# design.  They are the processor's own memory and MIO pins, they are identical
# in every Zynq design ever made, and drawn individually they bury the six
# blocks that are actually this design.  They are collapsed into the two
# interface ports DDR and FIXED_IO.
# ---------------------------------------------------------------------------
proc bd_to_dot {dotfile title} {
    set fh [open $dotfile w]
    puts $fh "digraph bd {"
    puts $fh "  rankdir=LR; splines=true; nodesep=0.4; ranksep=0.9;"
    puts $fh "  node \[shape=box style=rounded fontname=Helvetica fontsize=11\];"
    puts $fh "  graph \[label=\"$title\" labelloc=t fontsize=17 fontname=Helvetica\];"

    foreach c [get_bd_cells] {
        set vlnv [get_property VLNV $c]
        set nm   [file tail $c]
        set lbl  $nm
        if {$vlnv ne ""} { append lbl "\\n[lindex [split $vlnv :] 2]" }
        set extra "shape=box"
        if {[string match "*processing_system7*" $vlnv]} {
            set extra "shape=box3d style=\"rounded,filled\" fillcolor=\"#ffe8cc\""
        } elseif {[string match "*dmtd_capture*" $vlnv] || $nm eq "dmtd_capture_0"} {
            set extra "shape=box style=\"rounded,filled\" fillcolor=\"#d6f5d6\""
        }
        puts $fh "  \"$nm\" \[label=\"$lbl\" $extra\];"
    }

    # external ports, minus the PS boilerplate and the scalars that belong to
    # an interface port
    set skip {}
    foreach ip [get_bd_intf_ports] {
        lappend skip [file tail $ip]
    }
    foreach p [concat [get_bd_ports] [get_bd_intf_ports]] {
        set nm [file tail $p]
        if {[string match "DDR_*" $nm] || [string match "FIXED_IO_*" $nm]} { continue }
        set belongs 0
        foreach s $skip {
            if {$nm ne $s && [string match "${s}_*" $nm]} { set belongs 1; break }
        }
        if {$belongs} { continue }
        puts $fh "  \"$nm\" \[shape=invhouse style=filled fillcolor=\"#dde6f0\"\];"
    }

    foreach n [get_bd_intf_nets] {
        set ends {}
        foreach pin [get_bd_intf_pins -quiet -of_objects $n] {
            lappend ends [file tail [file dirname $pin]]
        }
        foreach prt [get_bd_intf_ports -quiet -of_objects $n] {
            lappend ends [file tail $prt]
        }
        set ends [lsort -unique $ends]
        if {[llength $ends] >= 2} {
            puts $fh "  \"[lindex $ends 0]\" -> \"[lindex $ends 1]\" \[label=\"[file tail $n]\" color=\"#1a4f8a\" fontsize=8 fontname=Helvetica\];"
        }
    }

    foreach n [get_bd_nets] {
        set prts [get_bd_ports -quiet -of_objects $n]
        if {[llength $prts] == 0} { continue }
        set pn [file tail [lindex $prts 0]]
        if {[string match "DDR_*" $pn] || [string match "FIXED_IO_*" $pn]} { continue }
        foreach pin [get_bd_pins -quiet -of_objects $n] {
            puts $fh "  \"$pn\" -> \"[file tail [file dirname $pin]]\" \[color=\"#1f7a1f\" fontsize=8\];"
        }
    }
    puts $fh "}"
    close $fh
}

proc bd_diagram {dotfile pdffile title} {
    bd_to_dot $dotfile $title
    if {[catch {exec dot -Tpdf $dotfile -o $pdffile} m]} {
        puts "NOTE: graphviz unavailable ($m); $dotfile is still written"
        return 0
    }
    puts "--- block diagram: $pdffile"
    return 1
}

# standalone use
if {[info exists argv] && [llength $argv] >= 2 && [string match "*.xpr" [lindex $argv 0]]} {
    open_project [lindex $argv 0]
    set bd [lindex $argv 1]
    open_bd_design [get_files $bd.bd]
    set d [file dirname [lindex $argv 0]]
    bd_diagram $d/../${bd}.dot $d/../${bd}_block_diagram.pdf "GPSDO DDMTD overlay - $bd"
    exit 0
}
