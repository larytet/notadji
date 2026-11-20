// cfr_fir - symmetric low-pass FIR with complex data and real Q15 coefficients (design/26-papr-dpd.md section 1.2).
module cfr_fir (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        s_valid,
    input  logic [31:0] s_data,
    output logic        m_valid,
    output logic [31:0] m_data
);
  localparam int CFR_TAPS = cfr_coef_pkg::CFR_TAPS;
  localparam int H = (CFR_TAPS - 1) / 2;
  function automatic logic signed [15:0] coef(input int k);
    coef = cfr_coef_pkg::CFR_COEF_FLAT[16*k +: 16];
  endfunction

  logic signed [15:0] di [CFR_TAPS];
  logic signed [15:0] dq [CFR_TAPS];

  // view of the delay line including the sample that enters now
  logic signed [15:0] ni [CFR_TAPS];
  logic signed [15:0] nq [CFR_TAPS];
  always_comb begin
    ni[0] = s_data[15:0];
    nq[0] = s_data[31:16];
    for (int k = 1; k < CFR_TAPS; k++) begin
      ni[k] = di[k-1];
      nq[k] = dq[k-1];
    end
  end

  // stage A: pair sums
  logic signed [16:0] pi [H+1];
  logic signed [16:0] pq [H+1];
  logic               va;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      va <= 1'b0;
      for (int k = 0; k < CFR_TAPS; k++) begin
        di[k] <= '0;
        dq[k] <= '0;
      end
      for (int k = 0; k <= H; k++) begin
        pi[k] <= '0;
        pq[k] <= '0;
      end
    end else begin
      va <= s_valid;
      if (s_valid) begin
        for (int k = 0; k < CFR_TAPS; k++) begin
          di[k] <= ni[k];
          dq[k] <= nq[k];
        end
        for (int k = 0; k < H; k++) begin
          pi[k] <= 17'(ni[k]) + 17'(ni[CFR_TAPS-1-k]);
          pq[k] <= 17'(nq[k]) + 17'(nq[CFR_TAPS-1-k]);
        end
        pi[H] <= 17'(ni[H]);
        pq[H] <= 17'(nq[H]);
      end
    end
  end

  // stage B: products
  logic signed [32:0] ti [H+1];
  logic signed [32:0] tq [H+1];
  logic               vb;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      vb <= 1'b0;
      for (int k = 0; k <= H; k++) begin
        ti[k] <= '0;
        tq[k] <= '0;
      end
    end else begin
      vb <= va;
      for (int k = 0; k <= H; k++) begin
        ti[k] <= pi[k] * coef(k);
        tq[k] <= pq[k] * coef(k);
      end
    end
  end

  // stage C: sum, round, saturate
  logic signed [40:0] si_, sq_;
  always_comb begin
    si_ = 41'sd16384;
    sq_ = 41'sd16384;
    for (int k = 0; k <= H; k++) begin
      si_ = si_ + 41'(ti[k]);
      sq_ = sq_ + 41'(tq[k]);
    end
  end
  function automatic logic [15:0] sat(input logic signed [40:0] a);
    logic signed [40:0] v;
    v = a >>> 15;
    if (v > 41'sd32767) sat = 16'h7FFF;
    else if (v < -41'sd32768) sat = 16'h8000;
    else sat = v[15:0];
  endfunction
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      m_valid <= 1'b0;
      m_data  <= '0;
    end else begin
      m_valid <= vb;
      m_data  <= {sat(sq_), sat(si_)};
    end
  end
endmodule
