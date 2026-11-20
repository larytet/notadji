// Test-only wrapper: receive and transmit correction blocks and the statistics accumulator with a selectable tap.
module cal_loop (
    input  logic        clk,
    input  logic        rst_n,
    // receive path
    input  logic        rx_cfg_valid,
    input  logic        rx_en,
    input  logic signed [15:0] rx_eps_r, rx_eps_i, rx_dc_i, rx_dc_q,
    input  logic        rx_valid,
    input  logic [31:0] rx_data,
    output logic        rx_m_valid,
    output logic [31:0] rx_m_data,
    // transmit path
    input  logic        tx_cfg_valid,
    input  logic        tx_en,
    input  logic signed [15:0] tx_eps_r, tx_eps_i, tx_dc_i, tx_dc_q,
    input  logic        tx_valid,
    input  logic [31:0] tx_data,
    output logic        tx_m_valid,
    output logic [31:0] tx_m_data,
    // statistics: tap 0 = raw receive input, 1 = corrected receive output
    input  logic        tap_sel,
    input  logic        st_clear,
    input  logic        st_start,
    input  logic [23:0] st_n,
    output logic        st_busy,
    output logic        st_done,
    output logic signed [39:0] sum_i, sum_q,
    output logic [47:0] sum_ii, sum_qq,
    output logic signed [47:0] sum_iq,
    output logic [31:0] st_count
);
  iq_corr u_rx (.clk(clk), .rst_n(rst_n), .cfg_valid(rx_cfg_valid), .en(rx_en), .dc_after(1'b0), .eps_r(rx_eps_r), .eps_i(rx_eps_i),
      .dc_i(rx_dc_i), .dc_q(rx_dc_q), .s_valid(rx_valid), .s_data(rx_data), .m_valid(rx_m_valid), .m_data(rx_m_data));
  iq_corr u_tx (.clk(clk), .rst_n(rst_n), .cfg_valid(tx_cfg_valid), .en(tx_en), .dc_after(1'b1), .eps_r(tx_eps_r), .eps_i(tx_eps_i),
      .dc_i(tx_dc_i), .dc_q(tx_dc_q), .s_valid(tx_valid), .s_data(tx_data), .m_valid(tx_m_valid), .m_data(tx_m_data));
  logic ovf;
  logic [15:0] ovr;
  cal_stats u_st (.clk(clk), .rst_n(rst_n), .clear(st_clear), .start(st_start), .n_samples(st_n), .s_valid(tap_sel ? rx_m_valid : rx_valid),
      .s_data(tap_sel ? rx_m_data : rx_data), .busy(st_busy), .done(st_done), .sum_i(sum_i), .sum_q(sum_q), .sum_ii(sum_ii), .sum_qq(sum_qq),
      .sum_iq(sum_iq), .count(st_count), .ovf(ovf), .ovr_cnt(ovr));
  wire unused_ok = &{1'b0, ovf, ovr};
endmodule
