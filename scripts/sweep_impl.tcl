set part xc7a35tcpg236-1
set top  am_modulator_top
set ooc  1

set script_dir [file dirname [file normalize [info script]]]
set root       [file normalize [file join $script_dir ..]]
set src_dir    [file join $root src]
set mem_dir    [file join $root mem]
set xdc_file   [file join $root constraint constraints.xdc]
set rpt_root   [file join $root results rpt]

proc collect_rtl {dir} {
    set files {}
    foreach f [lsort [glob -nocomplain -directory $dir *.v]] {
        set n [string tolower [file tail $f]]
        if {[string match "tb_*" $n] || [string match "*_tb.v" $n] || [string match "testbench*" $n]} continue
        lappend files $f
    }
    foreach d [lsort [glob -nocomplain -type d -directory $dir *]] {
        lappend files {*}[collect_rtl $d]
    }
    return $files
}

proc run_one {aw arch} {
    global part top ooc src_dir mem_dir xdc_file rpt_root

    set tag "AW${aw}_${arch}"
    set dir [file join $rpt_root $tag]
    file mkdir $dir

    set full_mem    [string map {\\ /} [file join $mem_dir "sine_full_AW${aw}.mem"]]
    set quarter_mem [string map {\\ /} [file join $mem_dir "sine_quarter_AW${aw}.mem"]]
    foreach m [list $full_mem $quarter_mem] {
        if {![file exists $m]} { error "Missing ROM file: $m" }
    }
    set use_quarter [expr {$arch eq "QUARTER" ? 1 : 0}]

    set files [collect_rtl $src_dir]
    if {[llength $files] == 0} { error "No .v files under $src_dir" }

    create_project -in_memory -part $part
    foreach f $files { read_verilog $f }
    read_xdc $xdc_file

    set args [list -top $top -part $part \
        -generic AW=$aw \
        -generic USE_QUARTER_ROM=$use_quarter \
        -generic FULL_MEM_FILE=\"$full_mem\" \
        -generic QUARTER_MEM_FILE=\"$quarter_mem\"]
    if {$ooc} { lappend args -mode out_of_context }

    synth_design {*}$args
    opt_design
    place_design
    route_design

    report_utilization    -file [file join $dir utilization.rpt]
    report_timing_summary -file [file join $dir timing.rpt]
    report_power          -file [file join $dir power.rpt]

    close_project
}

if {$argc == 2} {
    run_one [lindex $argv 0] [string toupper [lindex $argv 1]]
} elseif {$argc == 0} {
    foreach arch {FULL QUARTER} {
        foreach aw {8 10 12} {
            run_one $aw $arch
        }
    }
} else {
    error "Usage: -tclargs <AW> <FULL|QUARTER>, or no arguments for all six configurations"
}
