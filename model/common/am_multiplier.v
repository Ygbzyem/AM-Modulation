// Final AM product, Q11 fixed-point datapath.
module am_multiplier #(
    parameter DW = 12,
    parameter EW = DW + 2,
    parameter OW = 16
)(
    input  wire                 clk,
    input  wire                 rst,
    input  wire signed [EW-1:0] env,
    input  wire signed [DW-1:0] car,
    output reg  signed [OW-1:0] am_out
);

    wire signed [EW+DW-1:0] prod = env * car;

    always @(posedge clk) begin
        if (rst)
            am_out <= {OW{1'b0}};
        else
            am_out <= prod >>> (DW - 1);
    end
endmodule
