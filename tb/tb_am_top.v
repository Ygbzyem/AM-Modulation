`timescale 1ns / 1ps
module tb_am_top;

    // ---------------- configuration (edit these together) ----------------
    localparam integer AW              = 8;
    localparam integer USE_QUARTER_ROM = 0;
    localparam         FULL_MEM_FILE    = "sine_full_AW8.mem";
    localparam         QUARTER_MEM_FILE = "sine_quarter_AW8.mem";

    localparam [31:0]  FTW_CAR = 32'd42949673;  // 1 MHz at 100 MHz clock
    localparam [31:0]  FTW_MSG = 32'd858993;    // 20 kHz
    localparam [11:0]  AMP_CAR = 12'd2000;
    localparam [11:0]  AMP_MSG = 12'd1000;      // mu = AMP_MSG / AMP_CAR = 0.5

    localparam integer NUM_SAMPLES = 10000;
    localparam integer LATENCY     = 3;         // see header of am_modulator_top.v
    // ----------------------------------------------------------------------

    localparam integer CAR_PERIOD = (64'd1 << 32) / FTW_CAR + 1;  // samples per carrier cycle

    reg clk = 1'b0;
    reg rst = 1'b1;
    always #5 clk = ~clk;                       // 100 MHz

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

    // ---------------- reference model ----------------
    reg signed [11:0] ref_rom [0:(1 << AW) - 1];
    initial $readmemh(FULL_MEM_FILE, ref_rom);

    function integer ref_out;
        input [31:0] phase_car;
        input [31:0] phase_msg;
        integer car, msg, a_car, a_msg, msg_term, env;
        begin
            car      = ref_rom[phase_car[31 -: AW]];  // signed -> sign-extended
            msg      = ref_rom[phase_msg[31 -: AW]];
            a_car    = AMP_CAR;                       // unsigned -> zero-extended
            a_msg    = AMP_MSG;
            msg_term = (a_msg * msg) >>> 11;          // floor, same as the RTL
            env      = a_car + msg_term;
            ref_out  = (env * car) >>> 11;
        end
    endfunction

    // ---------------- checks ----------------
    integer n_pass = 0;
    integer n_fail = 0;
    integer n_skip = 0;

    task check;
        input            ok;
        input [8*56-1:0] text;
        begin
            if (ok) begin
                n_pass = n_pass + 1;
                $display("[PASS] %0s", text);
            end else begin
                n_fail = n_fail + 1;
                $display("[FAIL] %0s", text);
            end
        end
    endtask

    task skip;
        input [8*56-1:0] text;
        begin
            n_skip = n_skip + 1;
            $display("[SKIP] %0s", text);
        end
    endtask

    integer i, expected;
    integer mismatches, x_count, first_bad;
    integer out_max, out_min, win_max, peak_min;
    reg [31:0] ph_car, ph_msg;
    real ideal_max, ideal_trough, tol, mu_meas, mu_ideal;

    initial begin
        ftw_car = FTW_CAR;
        ftw_msg = FTW_MSG;
        amp_car = AMP_CAR;
        amp_msg = AMP_MSG;

        mismatches = 0;       x_count  = 0;     first_bad = -1;
        out_max    = -32768;  out_min  = 32767;
        win_max    = -32768;  peak_min = 32767;
        ph_car     = 32'd0;   ph_msg   = 32'd0;

        $display("--------------------------------------------------------");
        if (USE_QUARTER_ROM)
            $display("tb_am_top: AW=%0d ROM=QUARTER FTW_CAR=%0d FTW_MSG=%0d AMP_CAR=%0d AMP_MSG=%0d",
                     AW, FTW_CAR, FTW_MSG, AMP_CAR, AMP_MSG);
        else
            $display("tb_am_top: AW=%0d ROM=FULL FTW_CAR=%0d FTW_MSG=%0d AMP_CAR=%0d AMP_MSG=%0d",
                     AW, FTW_CAR, FTW_MSG, AMP_CAR, AMP_MSG);
        $display("--------------------------------------------------------");

        // 1. reset
        repeat (4) @(posedge clk);
        #1;
        check(am_out === 16'sd0, "am_out is 0 while reset is asserted");

        @(negedge clk);
        rst = 1'b0;

        for (i = 0; i < NUM_SAMPLES + LATENCY; i = i + 1) begin
            @(posedge clk);
            #1;
            if (i >= LATENCY) begin
                expected = ref_out(ph_car, ph_msg);
                ph_car   = ph_car + FTW_CAR;
                ph_msg   = ph_msg + FTW_MSG;

                if (^am_out === 1'bx) begin
                    x_count = x_count + 1;
                end else begin
                    if ($signed(am_out) != expected) begin
                        mismatches = mismatches + 1;
                        if (first_bad < 0) begin
                            first_bad = i - LATENCY;
                            $display("       first mismatch at sample %0d: rtl=%0d ref=%0d",
                                     first_bad, $signed(am_out), expected);
                        end
                    end
                    if ($signed(am_out) > out_max) out_max = $signed(am_out);
                    if ($signed(am_out) < out_min) out_min = $signed(am_out);

                    // the highest sample of each carrier cycle traces the envelope
                    if ($signed(am_out) > win_max) win_max = $signed(am_out);
                    if ((i - LATENCY) % CAR_PERIOD == CAR_PERIOD - 1) begin
                        if (win_max < peak_min) peak_min = win_max;
                        win_max = -32768;
                    end
                end
            end
        end

        // 2-3. bit-exact datapath
        check(x_count == 0,    "no X/Z on am_out after the pipeline fills");
        check(mismatches == 0, "bit-exact against the integer reference model");

        // 4-7. properties from AM theory, meaningful only for 0 < mu <= 1
        ideal_max    = (AMP_CAR + AMP_MSG) * 2047.0 / 2048.0;
        ideal_trough = (AMP_CAR - AMP_MSG) * 2047.0 / 2048.0;
        tol          = 0.01 * ideal_max + 1.0;
        $display("       am_out range %0d .. %0d, lowest carrier peak %0d",
                 out_min, out_max, peak_min);

        if (AMP_CAR != 0 && AMP_MSG != 0 && AMP_MSG <= AMP_CAR) begin
            check(out_max <= ideal_max + 1.0 && out_max >= ideal_max - tol,
                  "envelope peak ~ (amp_car + amp_msg) * 2047/2048");
            check(peak_min >= ideal_trough - tol && peak_min <= ideal_trough + tol,
                  "envelope trough ~ (amp_car - amp_msg) * 2047/2048");
            check(peak_min > 0 || AMP_MSG == AMP_CAR,
                  "envelope never crosses zero (mu <= 1)");
            mu_meas  = (out_max - peak_min) * 1.0 / (out_max + peak_min);
            mu_ideal = AMP_MSG * 1.0 / AMP_CAR;
            $display("       measured mu = %0.4f, expected %0.4f", mu_meas, mu_ideal);
            check(mu_meas > mu_ideal - 0.01 && mu_meas < mu_ideal + 0.01,
                  "measured modulation index within 0.01 of amp_msg/amp_car");
        end else begin
            skip("envelope peak (needs 0 < amp_msg <= amp_car)");
            skip("envelope trough");
            skip("envelope never crosses zero");
            skip("measured modulation index");
        end

        $display("--------------------------------------------------------");
        if (n_fail == 0)
            $display("RESULT: %0d/%0d PASS (%0d skipped)", n_pass, n_pass + n_fail, n_skip);
        else
            $display("RESULT: %0d FAIL, %0d PASS (%0d skipped)", n_fail, n_pass, n_skip);
        $display("--------------------------------------------------------");
        $finish;
    end

    initial begin
        #2_000_000;
        $display("ERROR: simulation timeout");
        $finish;
    end

endmodule
