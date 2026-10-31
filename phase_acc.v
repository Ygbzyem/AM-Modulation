`timescale 1ns / 1ps

module phase_acc #(
    parameter integer PW = 32
)(
    input  wire          clk,
    input  wire          rst,
    input  wire          en,
    input  wire [PW-1:0] ftw,

    output reg  [PW-1:0] phase
);

    always @(posedge clk) begin
        if (rst) begin
            phase <= {PW{1'b0}};
        end
        else if (en) begin
            phase <= phase + ftw;
        end
    end

endmodule