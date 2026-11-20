// budget_mon - bitstream-level check of the slice budget (design/28-encoder-wrapper.md section 1.3).
module budget_mon (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        clear,
    input  logic [15:0] budget,                 // bytes, sampled with the first byte of a slice
    input  logic        tap_valid,              // one pulse per byte entering the packetiser
    input  logic        tap_last,
    input  logic        buf_check_en,
    input  logic [15:0] fifo_level,             // bytes waiting between the encoder and the packetiser
    output logic        done,                   // pulse when a slice is complete
    output logic [15:0] size,
    output logic [15:0] ratio_q8,               // valid one clock after done
    output logic        over,
    output logic [15:0] max_ratio_q8,
    output logic [15:0] n_slices,
    output logic [15:0] n_over,
    output logic [15:0] n_zero_budget,
    output logic [15:0] err_buf
);
  logic        first;
  logic [15:0] bud, cnt;
  logic        buf_hit;
  logic        r_v;
  logic [15:0] r_size, r_bud;

  wire [15:0] bud_eff = first ? budget : bud;
  wire [15:0] cnt_eff = first ? 16'd1 : ((cnt == 16'hFFFF) ? cnt : cnt + 16'd1);
  wire [31:0] over_l = {16'd0, cnt_eff} * 32'd100;
  wire [31:0] over_r = {16'd0, bud_eff} * 32'd105;
  wire [31:0] rq = ({16'd0, r_size} << 8) / {16'd0, r_bud};
  wire [15:0] rq_s = (rq > 32'hFFFF) ? 16'hFFFF : rq[15:0];

  always_ff @(posedge clk) begin
    if (!rst_n || clear) begin
      first <= 1'b1;
      bud <= '0;
      cnt <= '0;
      buf_hit <= 1'b0;
      done <= 1'b0;
      size <= '0;
      ratio_q8 <= '0;
      over <= 1'b0;
      max_ratio_q8 <= '0;
      n_slices <= '0;
      n_over <= '0;
      n_zero_budget <= '0;
      err_buf <= '0;
      r_v <= 1'b0;
      r_size <= '0;
      r_bud <= 16'd1;
    end else begin
      done <= 1'b0;
      over <= 1'b0;
      r_v <= 1'b0;
      if (r_v) begin
        ratio_q8 <= rq_s;
        if (rq_s > max_ratio_q8) max_ratio_q8 <= rq_s;
      end
      if (tap_valid) begin
        if (first) buf_hit <= 1'b0;
        bud <= bud_eff;
        cnt <= tap_last ? 16'd0 : cnt_eff;
        if (buf_check_en && fifo_level > bud_eff && !(first ? 1'b0 : buf_hit)) begin
          buf_hit <= 1'b1;
          err_buf <= err_buf + 16'd1;
        end
        if (tap_last) begin
          done <= 1'b1;
          size <= cnt_eff;
          n_slices <= n_slices + 16'd1;
          if (bud_eff == 16'd0) n_zero_budget <= n_zero_budget + 16'd1;
          else begin
            if (over_l > over_r) begin
              over <= 1'b1;
              n_over <= n_over + 16'd1;
            end
            r_v <= 1'b1;
            r_size <= cnt_eff;
            r_bud <= bud_eff;
          end
        end
        first <= tap_last;
      end
    end
  end
endmodule
