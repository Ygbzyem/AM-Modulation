
`timescale 1ns / 1ps

module tb_am_modulator;

    // =========================================================
    // 1. Simulation parameters
    // =========================================================
    parameter integer NUM_SAMPLES = 100000;

    // =========================================================
    // 2. Testbench signals
    // =========================================================
    reg clk;
    reg rst;
    reg en;

    wire signed [15:0] am_out;
    wire signed [11:0] msg_out;
    wire signed [11:0] car_out;

    integer output_file;
    integer sample_count;

    // =========================================================
    // 3. Instantiate AM modulator
    // =========================================================
    am_modulator #(
        .PW(32),
        .AW(10),
        .DW(12),
        .FTW_CAR(32'd42949673),
        .FTW_MSG(32'd858993),
        .AMP_CAR(2000),
        .AMP_MSG(1000),
        .MEM_CAR("model/mem/sine_full_aw10.mem"),
        .MEM_MSG("model/mem/sine_full_aw10.mem")
    ) dut (
        .clk(clk),
        .rst(rst),
        .en(en),
        .am_out(am_out),
        .msg_out(msg_out),
        .car_out(car_out)
    );

    // =========================================================
    // 4. Generate 100 MHz clock
    // Clock period = 10 ns
    // =========================================================
    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    // =========================================================
    // 5. Run simulation and export CSV
    // =========================================================
    initial begin
        rst = 1'b1;
        en = 1'b0;
        sample_count = 0;

        // Open output CSV file
        output_file = $fopen("results/rtl_test.csv", "w");

        if (output_file == 0) begin
            $display("ERROR: Cannot open results/rtl_test.csv");
            $finish;
        end

        // CSV header
        $fdisplay(
            output_file,
            "Sample,MSG_Out,CAR_Out,AM_Out"
        );

        // Keep reset active for 5 clock cycles
        repeat (5) @(posedge clk);

        // Release reset and enable the modulator
        @(negedge clk);
        rst = 1'b0;
        en = 1'b1;

        // Collect simulation samples
        while (sample_count < NUM_SAMPLES) begin
            @(negedge clk);

            $fdisplay(
                output_file,
                "%0d,%0d,%0d,%0d",
                sample_count,
                $signed(msg_out),
                $signed(car_out),
                $signed(am_out)
            );

            sample_count = sample_count + 1;
        end

        // Close output file
        $fclose(output_file);

        $display("------------------------------------");
        $display("Simulation finished.");
        $display("Samples written: %0d", sample_count);
        $display("Output: results/rtl_test.csv");
        $display("------------------------------------");

        $finish;
    end

    // =========================================================
    // 6. Simulation timeout
    // =========================================================
    initial begin
        #2000000;
        $display("ERROR: Simulation timeout.");
        $finish;
    end

endmodule