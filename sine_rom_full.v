`timescale 1ns / 1ps

module sine_rom_full #(
    parameter AW = 8,
    parameter DW = 12,
    parameter MEM_FILE = "sine_full.mem"
)(
    input  wire                clk,
    input  wire [AW-1:0]       addr,
    output reg signed [DW-1:0] sine
);

    localparam ROM_DEPTH = (1 << AW);

    reg signed [DW-1:0] rom [0:ROM_DEPTH-1];
    reg signed [DW-1:0] sample_stage1;

    // Doc du lieu bang sin tu file .mem
    initial begin
        $readmemh(MEM_FILE, rom);
    end

    // Tang thanh ghi 1: tra cuu ROM
    // Tang thanh ghi 2: dang ky dau ra
    always @(posedge clk) begin
        sample_stage1 <= rom[addr];
        sine          <= sample_stage1;
    end

endmodule
```