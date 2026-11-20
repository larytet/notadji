// cfr_clip - soft clipper with a programmable gain table (design/26-papr-dpd.md section 1.1).
module cfr_clip (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        wr_en,
    input  logic [7:0]  wr_idx,
    input  logic [15:0] wr_g,                  // Q15, 32768 = 1.0
    input  logic        s_valid,
    input  logic [31:0] s_data,                // {Q, I} Q15
    output logic        m_valid,
    output logic [31:0] m_data
);
  logic [15:0] tab [256];
  wire signed [15:0] si = s_data[15:0];
  wire signed [15:0] sq = s_data[31:16];
  wire signed [31:0] ii = si * si;
  wire signed [31:0] qq = sq * sq;
  wire [31:0] m2 = 32'(ii) + 32'(qq);
  wire [9:0]  idx_full = m2[31:22];
  wire [7:0]  idx = (idx_full > 10'd255) ? 8'd255 : idx_full[7:0];

  wire unused_ok = &{1'b0, m2[21:0]};
  logic signed [15:0] r_i, r_q;
  logic [15:0] r_g;
  logic        v1;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      /* verilator lint_off BLKSEQ */
      for (int k = 0; k < 256; k++) tab[k] = 16'd32768;
      /* verilator lint_on BLKSEQ */
      v1 <= 1'b0;
      r_i <= '0;
      r_q <= '0;
      r_g <= 16'd32768;
      m_valid <= 1'b0;
      m_data  <= '0;
    end else begin
      if (wr_en) tab[wr_idx] <= wr_g;
      v1  <= s_valid;
      r_i <= si;
      r_q <= sq;
      r_g <= tab[idx];
      m_valid <= v1;
      m_data  <= {sat(r_q * $signed({1'b0, r_g})), sat(r_i * $signed({1'b0, r_g}))};
    end
  end
  function automatic logic [15:0] sat(input logic signed [32:0] p);
    logic signed [32:0] v;
    v = (p + 33'sd16384) >>> 15;
    if (v > 33'sd32767) sat = 16'h7FFF;
    else if (v < -33'sd32768) sat = 16'h8000;
    else sat = v[15:0];
  endfunction
endmodule
