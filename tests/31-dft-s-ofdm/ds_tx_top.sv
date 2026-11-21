// T31-09 test tops: the DFT-s blocks wired to the real mapper, IFFT, cyclic prefix and demapper.
module ds_tx_top (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  fft_log2,
    input  logic [1:0]  cp_sel,
    input  logic [2:0]  mod,
    input  logic [9:0]  shift_mask,
    input  logic        ref_boost,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,       // one constellation word per data symbol (M - 8 per OFDM symbol)
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic        m_axis_last
);
  logic        mm_v, mm_r, mm_l;
  logic [31:0] mm_d;
  mapper u_map (.clk(clk), .rst_n(rst_n), .mod(mod),
      .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready), .s_axis_data(s_axis_data), .s_axis_last(s_axis_last),
      .m_axis_valid(mm_v), .m_axis_ready(mm_r), .m_axis_data(mm_d), .m_axis_last(mm_l));
  logic        ds_v, ds_r, ds_l;
  logic [31:0] ds_d;
  logic [15:0] ovf_ds;
  logic        err_ds;
  dfts_tx u_ds (.clk(clk), .rst_n(rst_n), .fft_log2(fft_log2), .ref_boost(ref_boost),
      .s_axis_valid(mm_v), .s_axis_ready(mm_r), .s_axis_data(mm_d), .s_axis_last(mm_l),
      .m_axis_valid(ds_v), .m_axis_ready(ds_r), .m_axis_data(ds_d), .m_axis_last(ds_l), .ovf_cnt(ovf_ds), .err_len(err_ds));
  logic        ff_v, ff_r, ff_l;
  logic [31:0] ff_d;
  logic [15:0] ovf;
  logic        err_f;
  fft_core #(.MAX_LOG2(9)) u_fft (.clk(clk), .rst_n(rst_n), .fft_log2(fft_log2), .inverse(1'b1), .shift_mask(shift_mask),
      .s_axis_valid(ds_v), .s_axis_ready(ds_r), .s_axis_data(ds_d), .s_axis_last(ds_l),
      .m_axis_valid(ff_v), .m_axis_ready(ff_r), .m_axis_data(ff_d), .m_axis_last(ff_l), .ovf_cnt(ovf), .err_len(err_f));
  logic err_c;
  cp_insert #(.W(32), .MAX_LOG2(9)) u_cp (.clk(clk), .rst_n(rst_n), .fft_log2(fft_log2), .cp_sel(cp_sel),
      .s_axis_valid(ff_v), .s_axis_ready(ff_r), .s_axis_data(ff_d), .s_axis_last(ff_l),
      .m_axis_valid(m_axis_valid), .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data), .m_axis_last(m_axis_last), .err_len(err_c));
  wire unused_ok = &{1'b0, mm_l, ovf_ds, err_ds, ovf, err_f, err_c};
endmodule
