`timescale 1ns / 1ps

module nco #(
    parameter PW = 32,
    parameter AW = 8,
    parameter DW = 12,
    parameter USE_QUARTER_ROM = 0,
    parameter FULL_MEM_FILE = "sine_full.mem",
    parameter QUARTER_MEM_FILE = "sine_quarter.mem"
)(
    input  wire                 clk,
    input  wire                 rst,
    input  wire [PW-1:0]        ftw,
    output wire signed [DW-1:0] sine
);

    wire [PW-1:0] phase;
    wire [AW-1:0] rom_addr;

    // Lay AW bit cao cua pha lam dia chi ROM
    assign rom_addr = phase[PW-1:PW-AW];

    // Bo tich luy pha
    phase_acc #(
        .PW(PW)
    ) u_phase_acc (
        .clk   (clk),
        .rst   (rst),
        .ftw   (ftw),
        .phase (phase)
    );

    // Lua chon mot trong hai kien truc ROM
    generate
        if (USE_QUARTER_ROM != 0) begin : g_quarter_rom
            sine_rom_quarter #(
                .AW       (AW),
                .DW       (DW),
                .MEM_FILE (QUARTER_MEM_FILE)
            ) u_sine_rom (
                .clk  (clk),
                .addr (rom_addr),
                .sine (sine)
            );
        end else begin : g_full_rom
            sine_rom_full #(
                .AW       (AW),
                .DW       (DW),
                .MEM_FILE (FULL_MEM_FILE)
            ) u_sine_rom (
                .clk  (clk),
                .addr (rom_addr),
                .sine (sine)
            );
        end
    endgenerate

endmodule
```