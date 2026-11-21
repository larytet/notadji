// T31-09 test tops: the DFT-s blocks wired to the real mapper, IFFT, cyclic prefix and demapper.
module ds_rx_top (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  fft_log2,
    input  logic [2:0]  mod,
    input  logic [3:0]  llr_shift,
    input  logic        ref_boost,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [31:0] s_axis_data,
    input  logic [7:0]  s_csi,
    input  logic        s_axis_last,
    input  logic        lut_we,
    input  logic [7:0]  lut_addr,
    input  logic [8:0]  lut_data,
    input  logic [7:0]  csi_out,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [63:0] m_axis_data,       // eight 8-bit LLRs per data symbol
    output logic [3:0]  m_nbits,
    output logic        m_axis_last
);
  logic        d_v, d_r, d_l;
  logic [31:0] d_d;
  logic [7:0]  d_csi;
  logic [15:0] ovf;
  logic        err;
  dfts_rx u_rx (.clk(clk), .rst_n(rst_n), .fft_log2(fft_log2), .ref_boost(ref_boost),
      .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready), .s_axis_data(s_axis_data), .s_csi(s_csi), .s_axis_last(s_axis_last),
      .lut_we(lut_we), .lut_addr(lut_addr), .lut_data(lut_data), .csi_out(csi_out),
      .m_axis_valid(d_v), .m_axis_ready(d_r), .m_axis_data(d_d), .m_csi(d_csi), .m_axis_last(d_l), .ovf_cnt(ovf), .err_len(err));
  demapper u_dm (.clk(clk), .rst_n(rst_n), .mod(mod), .llr_shift(llr_shift),
      .s_axis_valid(d_v), .s_axis_ready(d_r), .s_axis_data(d_d), .s_csi(d_csi), .s_axis_last(d_l),
      .m_axis_valid(m_axis_valid), .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data), .m_nbits(m_nbits), .m_axis_last(m_axis_last));
  wire unused_ok = &{1'b0, ovf, err};
endmodule
