
`timescale 1ns / 1ps

module am_modulator #(
    parameter integer PW = 32,
    parameter integer AW = 10,
    parameter integer DW = 12,

    parameter [PW-1:0] FTW_CAR = 32'd42949673,
    parameter [PW-1:0] FTW_MSG = 32'd858993,

    parameter integer AMP_CAR = 2000,
    parameter integer AMP_MSG = 1000,

    parameter MEM_CAR = "model/mem/sine_full_aw10.mem",
    parameter MEM_MSG = "model/mem/sine_full_aw10.mem"
)(
    input wire clk,
    input wire rst,
    input wire en,

    output wire signed [15:0] am_out,
    output wire signed [DW-1:0] msg_out,
    output wire signed [DW-1:0] car_out
);

   

    nco #(
        .PW(PW),
        .AW(AW),
        .DW(DW),
        .USE_QUARTER_ROM(0),
        .FULL_MEM_FILE(MEM_MSG)
    ) u_msg_nco (
        .clk(clk),
        .rst(rst),
        .en(en),
        .ftw(FTW_MSG),
        .sine(msg_out)
    );

   

    nco #(
        .PW(PW),
        .AW(AW),
        .DW(DW),
        .USE_QUARTER_ROM(0),
        .FULL_MEM_FILE(MEM_CAR)
    ) u_car_nco (
        .clk(clk),
        .rst(rst),
        .en(en),
        .ftw(FTW_CAR),
        .sine(car_out)
    );

    wire signed [DW+1:0] envelope;

    am_envelope #(
        .DW(DW),
        .EW(DW+2)
    ) u_envelope (
        .clk(clk),
        .rst(rst),
        .msg(msg_out),
        .amp_car(AMP_CAR),
        .amp_msg(AMP_MSG),
        .env(envelope)
    );

    

    reg signed [DW-1:0] car_delay;

    always @(posedge clk) begin
        if (rst)
            car_delay <= {DW{1'b0}};
        else
            car_delay <= car_out;
    end

    wire signed [DW-1:0] car_aligned;

    assign car_aligned = car_delay;

 
    am_multiplier #(
        .DW(DW),
        .EW(DW+2),
        .OW(16)
    ) u_multiplier (
        .clk(clk),
        .rst(rst),
        .env(envelope),
        .car(car_aligned),
        .am_out(am_out)
    );

endmodule
