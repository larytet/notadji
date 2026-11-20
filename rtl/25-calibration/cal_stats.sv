// cal_stats - sample statistics for IQ and DC calibration (design/25-calibration.md section 2.1).
module cal_stats (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        clear,
    input  logic        start,
    input  logic [23:0] n_samples,
    input  logic        s_valid,
    input  logic [31:0] s_data,                 // {Q, I}
    output logic        busy,
    output logic        done,
    output logic signed [39:0] sum_i,
    output logic signed [39:0] sum_q,
    output logic [47:0] sum_ii,
    output logic [47:0] sum_qq,
    output logic signed [47:0] sum_iq,
    output logic [31:0] count,
    output logic        ovf,
    output logic [15:0] ovr_cnt
);
  logic [23:0] remain;
  wire signed [15:0] si = s_data[15:0];
  wire signed [15:0] sq = s_data[31:16];
  wire signed [31:0] ii = si * si;
  wire signed [31:0] qq = sq * sq;
  wire signed [31:0] iq = si * sq;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      busy    <= 1'b0;
      done    <= 1'b0;
      remain  <= '0;
      sum_i   <= '0;
      sum_q   <= '0;
      sum_ii  <= '0;
      sum_qq  <= '0;
      sum_iq  <= '0;
      count   <= '0;
      ovf     <= 1'b0;
      ovr_cnt <= '0;
    end else begin
      done <= 1'b0;
      if (clear) begin
        sum_i  <= '0;
        sum_q  <= '0;
        sum_ii <= '0;
        sum_qq <= '0;
        sum_iq <= '0;
        count  <= '0;
        ovf    <= 1'b0;
      end
      if (!busy) begin
        if (start) begin
          if (n_samples == 24'd0) done <= 1'b1;
          else begin
            busy   <= 1'b1;
            remain <= n_samples;
          end
        end
      end else begin
        if (start) ovr_cnt <= ovr_cnt + 16'd1;
        if (s_valid) begin
          if (!clear) begin
            sum_i  <= sum_i + 40'(si);
            sum_q  <= sum_q + 40'(sq);
            sum_ii <= sum_ii + 48'(ii);
            sum_qq <= sum_qq + 48'(qq);
            sum_iq <= sum_iq + 48'(iq);
            count  <= count + 32'd1;
            if (count >= 32'd131072) ovf <= 1'b1;
          end
          remain <= remain - 24'd1;
          if (remain == 24'd1) begin
            busy <= 1'b0;
            done <= 1'b1;
          end
        end
      end
    end
  end
endmodule
