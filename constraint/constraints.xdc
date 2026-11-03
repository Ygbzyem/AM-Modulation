create_clock -period 10.000 -name sys_clk [get_ports clk]

# Control inputs change far more slowly than the clock.
set_false_path -from [get_ports rst]
set_false_path -from [get_ports {ftw_car[*]}]
set_false_path -from [get_ports {ftw_msg[*]}]
set_false_path -from [get_ports {amp_car[*]}]
set_false_path -from [get_ports {amp_msg[*]}]

# The output is only observed in simulation, it is not bonded to a pin.
set_false_path -to [get_ports {am_out[*]}]