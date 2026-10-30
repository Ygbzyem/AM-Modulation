// AM envelope generator, Q11 fixed-point datapath.
// amp_car and amp_msg are non-negative magnitude controls.
module am_envelope #(
    parameter DW = 12,
    parameter EW = DW + 2
)(
    input  wire                 clk,
    input  wire                 rst,
    input  wire signed [DW-1:0] msg,
    input  wire        [DW-1:0] amp_car,
    input  wire        [DW-1:0] amp_msg,
    output reg  signed [EW-1:0] env
);

    // The leading zero keeps the non-negative amplitude signed during multiply.
    wire signed [2*DW:0] mult = $signed({1'b0, amp_msg}) * msg;
    wire signed [EW-1:0] msg_term = mult >>> (DW - 1);

    always @(posedge clk) begin
        if (rst)
            env <= {EW{1'b0}};
        else
            env <= $signed({2'b00, amp_car}) + msg_term;
    end
endmodule
