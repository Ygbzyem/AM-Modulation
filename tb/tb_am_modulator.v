
`timescale 1ns / 1ps

module tb_am_modulator;

    reg clk = 0;
    reg rst = 1;

    reg [31:0] ftw_car, ftw_msg;
    reg [11:0] amp_car, amp_msg;

    wire signed [15:0] am_out;

    integer fp;
    integer i;
    reg [255:0] outfile;

    always #5 clk = ~clk;

    top_module u_dut (
        .clk(clk),
        .rst(rst),
        .ftw_car(ftw_car),
        .ftw_msg(ftw_msg),
        .amp_car(amp_car),
        .amp_msg(amp_msg),
        .am_out(am_out)
    );

    initial begin
        if (!$value$plusargs("FTW_CAR=%d", ftw_car))
            ftw_car = 32'd42949673;

        if (!$value$plusargs("FTW_MSG=%d", ftw_msg))
            ftw_msg = 32'd858993;

        if (!$value$plusargs("AMP_CAR=%d", amp_car))
            amp_car = 12'd2000;

        if (!$value$plusargs("AMP_MSG=%d", amp_msg))
            amp_msg = 12'd1000;

        if (!$value$plusargs("OUTFILE=%s", outfile))
            outfile = "results/am_out.txt";

        fp = $fopen(outfile, "w");

        if (fp == 0) begin
            $display("ERROR: Khong mo duoc file output: %0s", outfile);
            $finish;
        end

        repeat (4) @(posedge clk);
        @(negedge clk);
        rst = 0;

        for (i = 0; i < 10000; i = i + 1) begin
            @(posedge clk);
            #1;
            $fwrite(fp, "%0d\n", $signed(am_out));
        end

        $fclose(fp);

        $display("Da ghi 10000 mau ra %0s", outfile);
        $finish;
    end

    initial begin
        #2000000;
        $display("ERROR: Simulation timeout.");
        $finish;
    end

endmodule
