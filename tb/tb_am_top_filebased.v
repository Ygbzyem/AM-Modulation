`timescale 1ns / 1ps
//==========================================================================
// tb_am_top_filebased.v - one configuration, set without editing this file.
//
// Stimulus is read from tb/am_config.txt (KEY = VALUE lines):
//     CASE, FC_HZ or FTW_CAR, FM_HZ or FTW_MSG, AMP_CAR, AMP_MSG, SAMPLES
// Edit the text file, save it, and run the simulation again.
//
// Priority, lowest to highest: defaults < am_config.txt < plusargs.
// Plusargs (+FTW_CAR=..., +AMP_MSG=..., +CONFIG=path, +OUTFILE=path) are
// still accepted for scripted runs.
//
// The config file is found at the first path that opens:
//     +CONFIG=<path>
//     ../../../../../tb/am_config.txt   (Vivado run directory .../behav/xsim)
//     tb/am_config.txt                  (simulator started at the repo root)
//     am_config.txt                     (simulator started inside tb/)
// Do not add am_config.txt to the Vivado project: Vivado would copy it into
// the run directory and the copy would go stale when you edit the original.
//
// AW and the ROM type change the hardware, so they are module parameters,
// set with generics before elaboration:
//     set_property generic {AW=10 USE_QUARTER_ROM=1
//         FULL_MEM_FILE="sine_full_AW10.mem"
//         QUARTER_MEM_FILE="sine_quarter_AW10.mem"} [get_filesets sim_1]
//
// Writes LATENCY + SAMPLES decimal samples to OUTFILE (default am_out.txt
// in the run directory). The first line is a header that
// golden_model/check_result.py reads to rebuild the same reference.
//==========================================================================
module tb_am_top_filebased #(
    parameter integer AW              = 8,
    parameter integer USE_QUARTER_ROM = 0,
    parameter         FULL_MEM_FILE    = "sine_full_AW8.mem",
    parameter         QUARTER_MEM_FILE = "sine_quarter_AW8.mem"
);

    localparam integer LATENCY     = 3;        // see header of am_modulator_top.v
    localparam integer MAX_SAMPLES = 1000000;  // 10 ms of simulated time
    localparam real    FTW_PER_HZ  = 4294967296.0 / 100.0e6;

    reg clk = 1'b0;
    reg rst = 1'b1;
    always #5 clk = ~clk;                      // 100 MHz

    reg  [31:0] ftw_car, ftw_msg;
    reg  [11:0] amp_car, amp_msg;
    wire signed [15:0] am_out;

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

    // ---------------- configuration ----------------
    reg  [8*256-1:0] cfg_path, outfile, line;
    reg  [8*32-1:0]  case_name, key, value;
    integer          num_samples, cfg_fd, n_fields, number, line_no, n_unknown;
    reg              parsed;
    reg  [63:0]      ftw_wide;

    // tuning word from a frequency in Hz, rounded to nearest
    function [31:0] ftw_from_hz;
        input integer hz;
        begin
            ftw_wide    = hz * FTW_PER_HZ;       // real -> integer rounds to nearest
            ftw_from_hz = ftw_wide[31:0];
        end
    endfunction

    // first non-NUL character of a string held in a reg
    function [7:0] first_char;
        input [8*32-1:0] text;
        integer b;
        begin
            first_char = 8'd0;
            for (b = 31; b >= 0; b = b - 1)
                if (first_char == 8'd0 && text[8*b +: 8] != 8'd0)
                    first_char = text[8*b +: 8];
        end
    endfunction

    task open_config;
        begin
            cfg_fd = 0;
            if ($value$plusargs("CONFIG=%s", cfg_path)) begin
                cfg_fd = $fopen(cfg_path, "r");
                if (cfg_fd == 0) $display("WARNING: cannot open +CONFIG=%0s", cfg_path);
            end
            if (cfg_fd == 0) begin cfg_path = "../../../../../tb/am_config.txt"; cfg_fd = $fopen(cfg_path, "r"); end
            if (cfg_fd == 0) begin cfg_path = "tb/am_config.txt";                cfg_fd = $fopen(cfg_path, "r"); end
            if (cfg_fd == 0) begin cfg_path = "am_config.txt";                   cfg_fd = $fopen(cfg_path, "r"); end
        end
    endtask

    task read_config;
        begin
            line_no   = 0;
            n_unknown = 0;
            while (!$feof(cfg_fd)) begin
                line = 0;
                if ($fgets(line, cfg_fd)) begin
                    line_no  = line_no + 1;
                    key      = 0;
                    value    = 0;
                    n_fields = $sscanf(line, "%s = %s", key, value);
                    if (n_fields == 2 && first_char(key) != "#") begin
                        number = 0;
                        parsed = (key == "CASE") || ($sscanf(value, "%d", number) == 1);
                        if (!parsed)
                            $display("WARNING: line %0d, '%0s' is not a number, line ignored", line_no, value);
                        else if (key == "CASE")    case_name   = value;
                        else if (key == "FC_HZ")   ftw_car     = ftw_from_hz(number);
                        else if (key == "FM_HZ")   ftw_msg     = ftw_from_hz(number);
                        else if (key == "FTW_CAR") ftw_car     = number;
                        else if (key == "FTW_MSG") ftw_msg     = number;
                        else if (key == "AMP_CAR") amp_car     = number;
                        else if (key == "AMP_MSG") amp_msg     = number;
                        else if (key == "SAMPLES") num_samples = number;
                        else begin
                            n_unknown = n_unknown + 1;
                            $display("WARNING: line %0d, unknown key '%0s'", line_no, key);
                        end
                        if ((key == "AMP_CAR" || key == "AMP_MSG") && (number < 0 || number > 4095))
                            $display("WARNING: line %0d, %0s = %0d is outside 0..4095 and is truncated to %0d",
                                     line_no, key, number, number % 4096);
                    end
                end
            end
            $fclose(cfg_fd);
        end
    endtask

    integer fp, i;

    initial begin
        // defaults
        ftw_car     = 32'd42949673;   // 1 MHz
        ftw_msg     = 32'd858993;     // 20 kHz
        amp_car     = 12'd2000;
        amp_msg     = 12'd1000;
        num_samples = 10000;
        case_name   = "single";
        outfile     = "am_out.txt";

        // config file
        open_config;
        if (cfg_fd != 0) begin
            read_config;
            $display("Config read from %0s", cfg_path);
        end else begin
            $display("WARNING: am_config.txt not found, using defaults");
        end

        // plusargs override the file
        if ($value$plusargs("FTW_CAR=%d", number)) ftw_car     = number;
        if ($value$plusargs("FTW_MSG=%d", number)) ftw_msg     = number;
        if ($value$plusargs("AMP_CAR=%d", number)) amp_car     = number;
        if ($value$plusargs("AMP_MSG=%d", number)) amp_msg     = number;
        if ($value$plusargs("SAMPLES=%d", number)) num_samples = number;
        if ($value$plusargs("CASE=%s", case_name)) ;
        if ($value$plusargs("OUTFILE=%s", outfile)) ;

        if (num_samples < 1 || num_samples > MAX_SAMPLES) begin
            $display("WARNING: SAMPLES = %0d out of range, using 10000", num_samples);
            num_samples = 10000;
        end

        $display("--------------------------------------------------------");
        $display("case %0s: AW=%0d ROM=%0s", case_name, AW, USE_QUARTER_ROM ? "QUARTER" : "FULL   ");
        $display("  FTW_CAR = %0d  (%0.1f Hz)", ftw_car, ftw_car / FTW_PER_HZ);
        $display("  FTW_MSG = %0d  (%0.1f Hz)", ftw_msg, ftw_msg / FTW_PER_HZ);
        $display("  AMP_CAR = %0d, AMP_MSG = %0d, SAMPLES = %0d", amp_car, amp_msg, num_samples);
        $display("--------------------------------------------------------");

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
                ftw_car, ftw_msg, amp_car, amp_msg, LATENCY, num_samples);

        repeat (4) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

        for (i = 0; i < num_samples + LATENCY; i = i + 1) begin
            @(posedge clk);
            #1;
            $fwrite(fp, "%0d\n", $signed(am_out));
        end

        $fclose(fp);
        $display("Wrote %0d samples (%0d warm-up) to %0s", num_samples + LATENCY, LATENCY, outfile);
        $finish;
    end

    initial begin
        #20_000_000;                  // 20 ms, above MAX_SAMPLES * 10 ns
        $display("ERROR: simulation timeout");
        $finish;
    end

endmodule
