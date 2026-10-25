`timescale 1ns / 1ps

module sine_rom_quarter #(
    parameter AW = 8,
    parameter DW = 12,
    parameter MEM_FILE = "sine_quarter.mem"
)(
    input  wire              clk,
    input  wire [AW-1:0]     addr,
    output reg signed [DW-1:0] sine
);

    // Kích th??c ROM thu g?n (1/4 chu k?)
    // Ví d?: AW = 8 thì ROM_DEPTH = 2^(8-2) = 64 ô nh?
    localparam QUARTER_DEPTH = 1 << (AW - 2);

    reg signed [DW-1:0] rom [0:QUARTER_DEPTH-1];

    // Tách các tín hi?u ?i?u khi?n t? ??a ch? pha ??u vào (addr t??ng ?ng v?i p)
    wire          half   = addr[AW-1];                    // N?a sau chu k? -> dùng ?? ??o d?u
    wire          mirror = addr[AW-2];                    // Góc ph?n t? 2 và 4 -> dùng ?? l?t ??a ch?
    wire [AW-3:0] q_addr = mirror ? ~addr[AW-3:0] : addr[AW-3:0]; // ??a ch? tra b?ng 1/4

    // Khai báo các thanh ghi trung gian cho pipeline (??m b?o ?úng 2 t?ng thanh ghi)
    reg signed [DW-1:0] mag;
    reg                 half_d;

    // ??c d? li?u b?ng tra 1/4 chu k? t? file .mem
    initial begin
        $readmemh(MEM_FILE, rom);
    end

    // T?ng thanh ghi 1: Tra c?u ROM và l?u tr?ng thái half
    // T?ng thanh ghi 2: ??o d?u d?a trên half_d tr? pha ?? t?o sóng sin hoàn ch?nh
    always @(posedge clk) begin
        mag    <= rom[q_addr];         // T?ng 1: ??c giá tr? biên ?? t? ROM thu g?n
        half_d <= half;          // T?ng 1: Tr? tín hi?u half 1 nh?p clock ?? ??ng b? v?i mag
        sine   <= half_d ? -mag : mag; // T?ng 2: ??o d?u n?u ? n?a sau chu k?
    end

endmodule