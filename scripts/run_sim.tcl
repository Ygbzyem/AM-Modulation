if {[info exists ::env(AM_WAVE)] && $::env(AM_WAVE) eq "1"} {
    log_wave -recursive *
}
run all
catch {quit}
