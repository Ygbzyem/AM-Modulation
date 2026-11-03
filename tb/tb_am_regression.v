`timescale 1ns / 1ps
//==========================================================================
// tb_am_regression.v - every verification case in one simulation run.
//
// Set as simulation top in Vivado and Run Behavioral Simulation. It writes
// rtl_case01.txt ... rtl_case18.txt into the simulator run directory
// (AM_Modulation_Vivado/AM_Modulation_Vivado.sim/sim_1/behav/xsim/).
// Then, from the repository root:
//     python golden_model/verify_rtl.py
// compares every file with the Python golden model and draws the
// golden-vs-RTL figures in results/<case>/.
//
// Each file starts with a header line holding the exact configuration, so
// the Python side never has to guess what the RTL was given.
//
//   01-07 functional   AW=8 FULL, varying mu / carrier / message
//   08-13 ROM sweep    AW=8,10,12 x FULL,QUARTER, default stimulus
//   14-18 edge cases   amplitude limits and tuning-word limits
//==========================================================================
module tb_am_regression;

    localparam integer NUM_SAMPLES = 10000;
    localparam integer LATENCY     = 3;

    localparam [31:0] FTW_CAR = 32'd42949673;   // 1 MHz
    localparam [31:0] FTW_MSG = 32'd858993;     // 20 kHz
    localparam [11:0] AMP_CAR = 12'd2000;
    localparam [11:0] AMP_MSG = 12'd1000;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    integer i, k;

    // ------------------------------------------------------------------
    // DUT for functional and edge cases: AW=8, FULL ROM, inputs changed
    // between cases with a reset in between.
    // ------------------------------------------------------------------
    reg         rst_f = 1'b1;
    reg  [31:0] f_ftw_car, f_ftw_msg;
    reg  [11:0] f_amp_car, f_amp_msg;
    wire signed [15:0] f_out;

    am_modulator_top #(.AW(8), .USE_QUARTER_ROM(0),
                       .FULL_MEM_FILE("sine_full_AW8.mem"),
                       .QUARTER_MEM_FILE("sine_quarter_AW8.mem"))
    u_func (.clk(clk), .rst(rst_f), .ftw_car(f_ftw_car), .ftw_msg(f_ftw_msg),
            .amp_car(f_amp_car), .amp_msg(f_amp_msg), .am_out(f_out));

    // ------------------------------------------------------------------
    // Six DUTs for the ROM sweep, all driven with the default stimulus.
    // ------------------------------------------------------------------
    reg rst_r = 1'b1;
    wire signed [15:0] r_out [0:5];

    am_modulator_top #(.AW(8),  .USE_QUARTER_ROM(0), .FULL_MEM_FILE("sine_full_AW8.mem"),  .QUARTER_MEM_FILE("sine_quarter_AW8.mem"))
    u_aw8_full     (.clk(clk), .rst(rst_r), .ftw_car(FTW_CAR), .ftw_msg(FTW_MSG), .amp_car(AMP_CAR), .amp_msg(AMP_MSG), .am_out(r_out[0]));
    am_modulator_top #(.AW(8),  .USE_QUARTER_ROM(1), .FULL_MEM_FILE("sine_full_AW8.mem"),  .QUARTER_MEM_FILE("sine_quarter_AW8.mem"))
    u_aw8_quarter  (.clk(clk), .rst(rst_r), .ftw_car(FTW_CAR), .ftw_msg(FTW_MSG), .amp_car(AMP_CAR), .amp_msg(AMP_MSG), .am_out(r_out[1]));
    am_modulator_top #(.AW(10), .USE_QUARTER_ROM(0), .FULL_MEM_FILE("sine_full_AW10.mem"), .QUARTER_MEM_FILE("sine_quarter_AW10.mem"))
    u_aw10_full    (.clk(clk), .rst(rst_r), .ftw_car(FTW_CAR), .ftw_msg(FTW_MSG), .amp_car(AMP_CAR), .amp_msg(AMP_MSG), .am_out(r_out[2]));
    am_modulator_top #(.AW(10), .USE_QUARTER_ROM(1), .FULL_MEM_FILE("sine_full_AW10.mem"), .QUARTER_MEM_FILE("sine_quarter_AW10.mem"))
    u_aw10_quarter (.clk(clk), .rst(rst_r), .ftw_car(FTW_CAR), .ftw_msg(FTW_MSG), .amp_car(AMP_CAR), .amp_msg(AMP_MSG), .am_out(r_out[3]));
    am_modulator_top #(.AW(12), .USE_QUARTER_ROM(0), .FULL_MEM_FILE("sine_full_AW12.mem"), .QUARTER_MEM_FILE("sine_quarter_AW12.mem"))
    u_aw12_full    (.clk(clk), .rst(rst_r), .ftw_car(FTW_CAR), .ftw_msg(FTW_MSG), .amp_car(AMP_CAR), .amp_msg(AMP_MSG), .am_out(r_out[4]));
    am_modulator_top #(.AW(12), .USE_QUARTER_ROM(1), .FULL_MEM_FILE("sine_full_AW12.mem"), .QUARTER_MEM_FILE("sine_quarter_AW12.mem"))
    u_aw12_quarter (.clk(clk), .rst(rst_r), .ftw_car(FTW_CAR), .ftw_msg(FTW_MSG), .amp_car(AMP_CAR), .amp_msg(AMP_MSG), .am_out(r_out[5]));

    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------
    reg [8*14-1:0] fname;                 // "rtl_caseNN.txt", exactly 14 chars
    integer        fd;
    integer        rom_fd [0:5];

    task open_case;
        input integer        idx;
        input [8*20-1:0]     name;
        input integer        aw;
        input integer        quarter;
        input [31:0]         ftw_car, ftw_msg;
        input [11:0]         amp_car, amp_msg;
        output integer       handle;
        begin
            $sformat(fname, "rtl_case%02d.txt", idx);
            handle = $fopen(fname, "w");
            if (handle == 0) begin
                $display("ERROR: cannot open %0s", fname);
                $finish;
            end
            // two branches: a ?: between strings of different length pads with NULs
            $fwrite(handle, "# case=%0s aw=%0d ", name, aw);
            if (quarter) $fwrite(handle, "rom=QUARTER ");
            else         $fwrite(handle, "rom=FULL ");
            $fwrite(handle, "ftw_car=%0d ftw_msg=%0d amp_car=%0d amp_msg=%0d latency=%0d samples=%0d\n",
                    ftw_car, ftw_msg, amp_car, amp_msg, LATENCY, NUM_SAMPLES);
        end
    endtask

    // one functional / edge case on u_func
    task run_func;
        input integer    idx;
        input [8*20-1:0] name;
        input [31:0]     ftw_car, ftw_msg;
        input [11:0]     amp_car, amp_msg;
        begin
            @(negedge clk);
            rst_f     = 1'b1;
            f_ftw_car = ftw_car;  f_ftw_msg = ftw_msg;
            f_amp_car = amp_car;  f_amp_msg = amp_msg;
            open_case(idx, name, 8, 0, ftw_car, ftw_msg, amp_car, amp_msg, fd);
            repeat (4) @(posedge clk);
            @(negedge clk);
            rst_f = 1'b0;
            for (i = 0; i < NUM_SAMPLES + LATENCY; i = i + 1) begin
                @(posedge clk);
                #1;
                $fwrite(fd, "%0d\n", $signed(f_out));
            end
            $fclose(fd);
            $display("  case %02d  %0s", idx, name);
        end
    endtask

    // ------------------------------------------------------------------
    // sequence
    // ------------------------------------------------------------------
    initial begin
        $display("--------------------------------------------------------");
        $display("tb_am_regression: writing rtl_case01..18.txt");
        $display("--------------------------------------------------------");

        // ROM sweep, six DUTs in parallel
        open_case( 8, "rom_aw8_full",     8, 0, FTW_CAR, FTW_MSG, AMP_CAR, AMP_MSG, rom_fd[0]);
        open_case( 9, "rom_aw8_quarter",  8, 1, FTW_CAR, FTW_MSG, AMP_CAR, AMP_MSG, rom_fd[1]);
        open_case(10, "rom_aw10_full",   10, 0, FTW_CAR, FTW_MSG, AMP_CAR, AMP_MSG, rom_fd[2]);
        open_case(11, "rom_aw10_quarter",10, 1, FTW_CAR, FTW_MSG, AMP_CAR, AMP_MSG, rom_fd[3]);
        open_case(12, "rom_aw12_full",   12, 0, FTW_CAR, FTW_MSG, AMP_CAR, AMP_MSG, rom_fd[4]);
        open_case(13, "rom_aw12_quarter",12, 1, FTW_CAR, FTW_MSG, AMP_CAR, AMP_MSG, rom_fd[5]);
        repeat (4) @(posedge clk);
        @(negedge clk);
        rst_r = 1'b0;
        for (i = 0; i < NUM_SAMPLES + LATENCY; i = i + 1) begin
            @(posedge clk);
            #1;
            for (k = 0; k < 6; k = k + 1)
                $fwrite(rom_fd[k], "%0d\n", $signed(r_out[k]));
        end
        for (k = 0; k < 6; k = k + 1)
            $fclose(rom_fd[k]);
        $display("  cases 08-13  ROM sweep");

        // functional cases
        run_func( 1, "functional_mu_0",    FTW_CAR, FTW_MSG,      AMP_CAR, 12'd0);
        run_func( 2, "functional_mu_0.25", FTW_CAR, FTW_MSG,      AMP_CAR, 12'd500);
        run_func( 3, "functional_mu_0.5",  FTW_CAR, FTW_MSG,      AMP_CAR, 12'd1000);
        run_func( 4, "functional_mu_1",    FTW_CAR, FTW_MSG,      AMP_CAR, 12'd2000);
        run_func( 5, "functional_mu_1.5",  FTW_CAR, FTW_MSG,      AMP_CAR, 12'd3000);
        run_func( 6, "functional_dsb_sc",  FTW_CAR, FTW_MSG,      12'd0,   AMP_MSG);
        run_func( 7, "functional_fm_100k", FTW_CAR, 32'd4294967,  AMP_CAR, AMP_MSG);

        // edge cases
        run_func(14, "edge_amp_max",       FTW_CAR, FTW_MSG,      12'd4095, 12'd4095);
        run_func(15, "edge_dsb_max",       FTW_CAR, FTW_MSG,      12'd0,    12'd4095);
        run_func(16, "edge_ftw_nyquist",   32'h8000_0000, FTW_MSG, AMP_CAR, AMP_MSG);
        run_func(17, "edge_ftw_max",       32'hFFFF_FFFF, FTW_MSG, AMP_CAR, AMP_MSG);
        run_func(18, "edge_ftw_zero",      32'd0,   FTW_MSG,      AMP_CAR, AMP_MSG);

        $display("--------------------------------------------------------");
        $display("Done. Run: python golden_model/verify_rtl.py");
        $display("--------------------------------------------------------");
        $finish;
    end

endmodule
