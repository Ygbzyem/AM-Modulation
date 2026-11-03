`timescale 1ns / 1ps
// AM modulator (DSB-FC), Q11 fixed-point datapath.
//
// Register stages after the phase accumulator:
//   ROM stage 1 -> ROM stage 2 -> envelope (carrier: car_d1) -> multiplier
// The phase register output phase[n] therefore reaches am_out four clock
// edges later. A testbench that releases reset and samples am_out after
// every rising edge sees reference sample n at its own sample index n + 3,
// because phase[0] (the reset value) already sits at the ROM input during
// reset. See tb/tb_am_top.v.
//
// MEM_FILE parameters are bare file names: add the mem/*.mem files to the
// Vivado project so that both simulation and synthesis can find them.
module am_modulator_top #(
    parameter integer PW = 32,
    parameter integer AW = 8,
    parameter integer DW = 12,
    parameter integer OW = 16,
    parameter integer USE_QUARTER_ROM = 0,
    parameter FULL_MEM_FILE    = "sine_full_AW8.mem",
    parameter QUARTER_MEM_FILE = "sine_quarter_AW8.mem"
)(
    input wire clk,
    input wire rst,

    input wire [PW-1:0] ftw_car,
    input wire [PW-1:0] ftw_msg,
    input wire [DW-1:0] amp_car,
    input wire [DW-1:0] amp_msg,

    output wire signed [OW-1:0] am_out
);

    wire signed [DW-1:0] car;
    wire signed [DW-1:0] msg;
    wire signed [DW-1:0] car_aligned;
    wire signed [DW+1:0] env;

    // Delay the carrier by one clock so it meets the registered envelope.
    reg signed [DW-1:0] car_d1;

    always @(posedge clk) begin
        if (rst)
            car_d1 <= {DW{1'b0}};
        else
            car_d1 <= car;
    end

    assign car_aligned = car_d1;

    // Carrier NCO
    nco #(
        .PW(PW),
        .AW(AW),
        .DW(DW),
        .USE_QUARTER_ROM(USE_QUARTER_ROM),
        .FULL_MEM_FILE(FULL_MEM_FILE),
        .QUARTER_MEM_FILE(QUARTER_MEM_FILE)
    ) u_car (
        .clk(clk),
        .rst(rst),
        .en(1'b1),
        .ftw(ftw_car),
        .sine(car)
    );

    // Message NCO
    nco #(
        .PW(PW),
        .AW(AW),
        .DW(DW),
        .USE_QUARTER_ROM(USE_QUARTER_ROM),
        .FULL_MEM_FILE(FULL_MEM_FILE),
        .QUARTER_MEM_FILE(QUARTER_MEM_FILE)
    ) u_msg (
        .clk(clk),
        .rst(rst),
        .en(1'b1),
        .ftw(ftw_msg),
        .sine(msg)
    );

    // AM envelope
    am_envelope #(
        .DW(DW),
        .EW(DW+2)
    ) u_env (
        .clk(clk),
        .rst(rst),
        .msg(msg),
        .amp_car(amp_car),
        .amp_msg(amp_msg),
        .env(env)
    );

    // AM multiplier
    am_multiplier #(
        .DW(DW),
        .EW(DW+2),
        .OW(OW)
    ) u_mul (
        .clk(clk),
        .rst(rst),
        .env(env),
        .car(car_aligned),
        .am_out(am_out)
    );

endmodule

