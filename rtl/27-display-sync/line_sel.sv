// line_sel - per-line freshness of the frame being decoded and buffer selection for the scan-out (design/27-display-sync.md section 1.4).
module line_sel (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        swap,
    input  logic        wr_valid,
    input  logic [10:0] wr_line,
    input  logic [10:0] wr_n,
    input  logic        rd_req,
    input  logic [10:0] rd_line,
    output logic        use_cur,
    output logic        buf_sel,
    output logic        rd_valid,
    output logic        cur_buf,
    output logic [15:0] stale_cnt,
    output logic [15:0] cur_cnt,
    output logic [15:0] late_wr_cnt
);
  logic [2047:0] fresh;
  logic [15:0] stale_run, cur_run;
  logic [11:0] scanned;                 // lines requested so far in this frame (highest request + 1)
  wire [11:0] wr_end = {1'b0, wr_line} + {1'b0, wr_n};

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      fresh <= '0;
      stale_run <= '0;
      cur_run <= '0;
      scanned <= '0;
      use_cur <= 1'b0;
      buf_sel <= 1'b0;
      rd_valid <= 1'b0;
      cur_buf <= 1'b0;
      stale_cnt <= '0;
      cur_cnt <= '0;
      late_wr_cnt <= '0;
    end else begin
      rd_valid <= 1'b0;
      if (swap) begin
        cur_buf <= ~cur_buf;
        fresh <= '0;
        stale_cnt <= stale_run;
        cur_cnt <= cur_run;
        stale_run <= '0;
        cur_run <= '0;
        scanned <= '0;
      end else begin
        if (wr_valid) begin
          for (int i = 0; i < 2048; i++) begin
            if (i >= int'(wr_line) && i < int'(wr_end)) fresh[i] <= 1'b1;
          end
          if ({1'b0, wr_line} < scanned) late_wr_cnt <= late_wr_cnt + 16'd1;
        end
        if (rd_req) begin
          use_cur <= fresh[rd_line];
          buf_sel <= fresh[rd_line] ? cur_buf : ~cur_buf;
          rd_valid <= 1'b1;
          if (fresh[rd_line]) cur_run <= cur_run + 16'd1;
          else stale_run <= stale_run + 16'd1;
          if ({1'b0, rd_line} + 12'd1 > scanned) scanned <= {1'b0, rd_line} + 12'd1;
        end
      end
    end
  end
endmodule
