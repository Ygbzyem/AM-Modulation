`timescale 1ns / 1ps

module phase_acc #(
    parameter PW = 32
)(
    input  wire          clk,
    input  wire          rst,
    input  wire [PW-1:0] ftw,
    output reg  [PW-1:0] phase
);

    always @(posedge clk) begin
        if (rst)
            phase <= {PW{1'b0}};
        else
            phase <= phase + ftw;
    end

endmodule
```