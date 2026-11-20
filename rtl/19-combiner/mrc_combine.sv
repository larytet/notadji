// mrc_combine - per-tone maximum-ratio combining of B equalised branches (design/19-combiner.md).
module mrc_combine #(
    parameter int B = 2                 // 2..8
) (
    input  logic            clk,
    input  logic            rst_n,
    input  logic [B-1:0]    s_valid,
    output logic [B-1:0]    s_ready,
    input  logic [32*B-1:0] s_data,     // branch b in bits 32b+31..32b, {Q, I}
    input  logic [8*B-1:0]  s_csi,
    input  logic [B-1:0]    s_last,
    output logic            m_valid,
    input  logic            m_ready,
    output logic [31:0]     m_data,
    output logic [7:0]      m_csi,
    output logic            m_last,
    output logic            err_len
);
  wire all_v   = &s_valid;
  wire can_out = ~m_valid | m_ready;
  wire fire    = all_v & can_out;
  assign s_ready = {B{fire}};

  // sums
  logic [10:0]        ssum;
  logic signed [27:0] num_i, num_q;
  always_comb begin
    ssum  = 11'd0;
    num_i = 28'sd0;
    num_q = 28'sd0;
    for (int b = 0; b < B; b++) begin
      ssum  = ssum + 11'(s_csi[8*b +: 8]);
      num_i = num_i + 28'($signed(s_data[32*b +: 16]) * $signed({1'b0, s_csi[8*b +: 8]}));
      num_q = num_q + 28'($signed(s_data[32*b + 16 +: 16]) * $signed({1'b0, s_csi[8*b +: 8]}));
    end
  end

  // reciprocal: r = 2^34 / S via the table of module 17
  logic [3:0]  pos;
  logic [7:0]  idx;
  logic [15:0] tval;
  always_comb begin
    pos = 4'd0;
    for (int i = 0; i < 11; i++) if (ssum[i]) pos = 4'(i);
    if (pos >= 4'd8) idx = 8'((ssum >> (pos - 4'd8)) - 11'd256);
    else idx = 8'((ssum << (4'd8 - pos)) - 11'd256);
  end
  recip_rom u_rom (.idx(idx), .t(tval));
  wire [34:0] rq = 35'(tval) << (5'd19 - {1'b0, pos});
  wire signed [36:0] rs = $signed({2'b00, rq});

  wire signed [64:0] pi_raw = num_i * rs;                    // 28 x 37 bit
  wire signed [64:0] pq_raw = num_q * rs;
  wire signed [64:0] zi_ = (pi_raw + 65'sd8589934592) >>> 34;   // + 2^33: rounding
  wire signed [64:0] zq_ = (pq_raw + 65'sd8589934592) >>> 34;

  function automatic [15:0] sat16(input signed [64:0] v);
    begin
      if (v > 65'sd32767) sat16 = 16'sd32767;
      else if (v < -65'sd32768) sat16 = 16'h8000;
      else sat16 = v[15:0];
    end
  endfunction

  wire lasts_equal = (&s_last) | ~(|s_last);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      m_valid <= 1'b0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      if (m_valid && m_ready) m_valid <= 1'b0;
      if (fire) begin
        m_valid <= 1'b1;
        m_data  <= (ssum == 11'd0) ? 32'd0 : {sat16(zq_), sat16(zi_)};
        m_csi   <= (ssum > 11'd255) ? 8'd255 : ssum[7:0];
        m_last  <= s_last[0];
        if (!lasts_equal) err_len <= 1'b1;
      end
    end
  end
endmodule
