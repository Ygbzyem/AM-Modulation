`timescale 1ns / 1ps

module sine_rom_quarter #(
    parameter integer AW = 8,
    parameter integer DW = 12,
    parameter MEM_FILE = "model/mem/sine_quarter_aw8.mem"
)(
    input  wire                clk,
    input  wire [AW-1:0]       addr,
    output reg signed [DW-1:0] sine
);

    localparam integer QUARTER_BITS = AW - 2;
    localparam integer QUARTER_DEPTH = (1 << QUARTER_BITS);

    wire quadrant = addr[AW-1];
    wire mirror   = addr[AW-2];

    wire [QUARTER_BITS-1:0] quarter_addr;
    wire [QUARTER_BITS-1:0] rom_addr;

    assign quarter_addr = addr[QUARTER_BITS-1:0];

    // Reflect the address in the second half of each sine half-wave.
    assign rom_addr = mirror ? ~quarter_addr : quarter_addr;

    reg signed [DW-1:0] rom [0:QUARTER_DEPTH-1];

    reg signed [DW-1:0] sample_stage1;
    reg                 sign_stage1;

    initial begin
        $readmemh(MEM_FILE, rom);
    end

    // Two registered stages, matching sine_rom_full.v.
    always @(posedge clk) begin
        sample_stage1 <= rom[rom_addr];
        sign_stage1   <= quadrant;

        if (sign_stage1)
            sine <= -sample_stage1;
        else
            sine <= sample_stage1;
    end

endmodule