`timescale 1ns / 1ps
module tb_am_top_filebased #(
    parameter integer AW              = 8,
    parameter integer USE_QUARTER_ROM = 0,
    parameter         FULL_MEM_FILE    = "sine_full_AW8.mem",
    parameter         QUARTER_MEM_FILE = "sine_quarter_AW8.mem"
);

    localparam integer NUM_SAMPLES = 10000;
    localparam integer LATENCY     = 3;   // see header of am_modulator_top.v

    reg clk = 1'b0;
    reg rst = 1'b1;
    always #5 clk = ~clk;                 // 100 MHz

    reg  [31:0] ftw_car, ftw_msg;
    reg  [11:0] amp_car, amp_msg;
    wire signed [15:0] am_out;

    reg  [8*256-1:0] outfile;
    reg  [8*32-1:0]  case_name;
    integer fp, i;

    am_modulator_top #(
        .AW               (AW),
        .USE_QUARTER_ROM  (USE_QUARTER_ROM),
        .FULL_MEM_FILE    (FULL_MEM_FILE),
        .QUARTER_MEM_FILE (QUARTER_MEM_FILE)
    ) u_dut (
        .clk     (clk),
        .rst     (rst),
        .ftw_car (ftw_car),
        .ftw_msg (ftw_msg),
        .amp_car (amp_car),
        .amp_msg (amp_msg),
        .am_out  (am_out)
    );

    initial begin
        if (!$value$plusargs("FTW_CAR=%d", ftw_car))   ftw_car   = 32'd42949673;
        if (!$value$plusargs("FTW_MSG=%d", ftw_msg))   ftw_msg   = 32'd858993;
        if (!$value$plusargs("AMP_CAR=%d", amp_car))   amp_car   = 12'd2000;
        if (!$value$plusargs("AMP_MSG=%d", amp_msg))   amp_msg   = 12'd1000;
        if (!$value$plusargs("OUTFILE=%s", outfile))   outfile   = "am_out.txt";
        if (!$value$plusargs("CASE=%s",    case_name)) case_name = "single";

        fp = $fopen(outfile, "w");
        if (fp == 0) begin
            $display("ERROR: cannot open output file %0s", outfile);
            $finish;
        end

        // two branches: a ?: between strings of different length pads with NULs
        $fwrite(fp, "# case=%0s aw=%0d ", case_name, AW);
        if (USE_QUARTER_ROM) $fwrite(fp, "rom=QUARTER ");
        else                 $fwrite(fp, "rom=FULL ");
        $fwrite(fp, "ftw_car=%0d ftw_msg=%0d amp_car=%0d amp_msg=%0d latency=%0d samples=%0d\n",
                ftw_car, ftw_msg, amp_car, amp_msg, LATENCY, NUM_SAMPLES);

        repeat (4) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

        for (i = 0; i < NUM_SAMPLES + LATENCY; i = i + 1) begin
            @(posedge clk);
            #1;
            $fwrite(fp, "%0d\n", $signed(am_out));
        end

        $fclose(fp);
        $display("Wrote %0d samples (%0d warm-up) to %0s", NUM_SAMPLES + LATENCY, LATENCY, outfile);
        $finish;
    end

    initial begin
        #2_000_000;
        $display("ERROR: simulation timeout");
        $finish;
    end

endmodule
