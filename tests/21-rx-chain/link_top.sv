// Test-only wrapper: transmit chain and receive chain side by side (the channel is modelled in the testbench).
module link_top (
    input  logic        clk,
    input  logic        rst_n,
    // transmitter
    input  logic [3:0]  tx_fft_log2,
    input  logic [1:0]  tx_cp_sel,
    input  logic [2:0]  tx_mod,
    input  logic [2:0]  tx_code,
    input  logic [9:0]  tx_shift_mask,
    input  logic        tx_s_valid,
    output logic        tx_s_ready,
    input  logic [7:0]  tx_s_data,
    input  logic        tx_s_last,
    output logic        tx_m_valid,
    input  logic        tx_m_ready,
    output logic [31:0] tx_m_data,
    output logic        tx_m_last,
    output logic        tx_err,
    // receiver
    input  logic [3:0]  rx_fft_log2,
    input  logic [1:0]  rx_cp_sel,
    input  logic [2:0]  rx_mod,
    input  logic [2:0]  rx_code,
    input  logic [15:0] rx_nsym,
    input  logic [7:0]  rx_ncw,
    input  logic [15:0] rx_nbytes,
    input  logic [3:0]  rx_backoff,
    input  logic [1:0]  rx_thr_sel,
    input  logic [31:0] rx_min_power,
    input  logic        rx_s_valid,
    input  logic [31:0] rx_s_data,
    output logic        rx_m_valid,
    input  logic        rx_m_ready,
    output logic [7:0]  rx_m_data,
    output logic        rx_m_last,
    output logic        rx_frame_ok,
    output logic [5:0]  rx_iters_max,
    output logic        rx_det,
    output logic signed [23:0] rx_cfo_inc,
    output logic [12:0] rx_fifo_max,
    output logic        rx_err
);
  tx_chain u_tx (
      .clk(clk), .rst_n(rst_n), .fft_log2(tx_fft_log2), .cp_sel(tx_cp_sel), .mod(tx_mod), .code(tx_code), .shift_mask(tx_shift_mask),
      .s_axis_valid(tx_s_valid), .s_axis_ready(tx_s_ready), .s_axis_data(tx_s_data), .s_axis_last(tx_s_last),
      .m_axis_valid(tx_m_valid), .m_axis_ready(tx_m_ready), .m_axis_data(tx_m_data), .m_axis_last(tx_m_last), .err(tx_err));
  rx_chain u_rx (
      .clk(clk), .rst_n(rst_n), .fft_log2(rx_fft_log2), .cp_sel(rx_cp_sel), .mod(rx_mod), .code(rx_code), .nsym(rx_nsym), .ncw(rx_ncw),
      .nbytes(rx_nbytes), .backoff(rx_backoff), .thr_sel(rx_thr_sel), .min_power(rx_min_power),
      .s_valid(rx_s_valid), .s_data(rx_s_data),
      .m_axis_valid(rx_m_valid), .m_axis_ready(rx_m_ready), .m_axis_data(rx_m_data), .m_axis_last(rx_m_last),
      .frame_ok(rx_frame_ok), .iters_max(rx_iters_max), .det(rx_det), .cfo_inc(rx_cfo_inc), .fifo_max(rx_fifo_max), .err(rx_err));
endmodule
