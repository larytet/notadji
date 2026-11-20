// iq_corr - DC and IQ-imbalance correction x' = z - e z* (design/25-calibration.md section 2.2).
module iq_corr (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        cfg_valid,
    input  logic        en,
    input  logic        dc_after,                // 0: subtract dc before the matrix (receive), 1: add dc after it (transmit)
    input  logic signed [15:0] eps_r,
    input  logic signed [15:0] eps_i,
    input  logic signed [15:0] dc_i,
    input  logic signed [15:0] dc_q,
    input  logic        s_valid,
    input  logic [31:0] s_data,
    output logic        m_valid,
    output logic [31:0] m_data
);
  logic              r_en, r_da;
  logic signed [15:0] r_er, r_ei, r_di, r_dq;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      r_en <= 1'b0;
      r_da <= 1'b0;
      r_er <= '0;
      r_ei <= '0;
      r_di <= '0;
      r_dq <= '0;
    end else if (cfg_valid) begin
      r_en <= en;
      r_da <= dc_after;
      r_er <= eps_r;
      r_ei <= eps_i;
      r_di <= dc_i;
      r_dq <= dc_q;
    end
  end

  // stage 1: subtract the DC (receive mode)
  logic signed [16:0] xi, xq;
  logic               v1;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      v1 <= 1'b0;
      xi <= '0;
      xq <= '0;
    end else begin
      v1 <= s_valid;
      if (r_en && !r_da) begin
        xi <= 17'($signed(s_data[15:0])) - 17'(r_di);
        xq <= 17'($signed(s_data[31:16])) - 17'(r_dq);
      end else begin
        xi <= 17'($signed(s_data[15:0]));
        xq <= 17'($signed(s_data[31:16]));
      end
    end
  end

  // stage 2: products
  logic signed [32:0] p1, p2, p3, p4;
  logic signed [16:0] yi0, yq0;
  logic               v2;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      v2  <= 1'b0;
      p1  <= '0;
      p2  <= '0;
      p3  <= '0;
      p4  <= '0;
      yi0 <= '0;
      yq0 <= '0;
    end else begin
      v2  <= v1;
      p1  <= xi * r_er;
      p2  <= xq * r_ei;
      p3  <= xi * r_ei;
      p4  <= xq * r_er;
      yi0 <= xi;
      yq0 <= xq;
    end
  end

  // stage 3: matrix, rounding, optional DC add, saturation
  wire signed [33:0] ci = 34'(p1) + 34'(p2) + 34'sd16384;
  wire signed [33:0] cq = 34'(p3) - 34'(p4) + 34'sd16384;
  wire signed [18:0] ri = 19'(yi0) - 19'(ci >>> 15) + ((r_en && r_da) ? 19'(r_di) : 19'sd0);
  wire signed [18:0] rq = 19'(yq0) - 19'(cq >>> 15) + ((r_en && r_da) ? 19'(r_dq) : 19'sd0);
  wire signed [18:0] ei = r_en ? ri : 19'(yi0);
  wire signed [18:0] eq = r_en ? rq : 19'(yq0);
  function automatic logic [15:0] sat16(input logic signed [18:0] v);
    if (v > 19'sh07FFF) sat16 = 16'h7FFF;
    else if (v < 19'sh78000) sat16 = 16'h8000;
    else sat16 = v[15:0];
  endfunction
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      m_valid <= 1'b0;
      m_data  <= '0;
    end else begin
      m_valid <= v2;
      m_data  <= {sat16(eq), sat16(ei)};
    end
  end
endmodule
