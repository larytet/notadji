// radio_if - radio interface wrapper: sample paths, SPI, control pins (design/11-radio-interface.md).
module radio_if #(
    parameter int AW = 4
) (
    input  logic        clk,
    input  logic        rst_n,
    // radio clock domains
    input  logic        rx_clk,
    input  logic        rx_rst_n,
    input  logic        rx_valid,
    input  logic [31:0] rx_data,
    input  logic        tx_clk,
    input  logic        tx_rst_n,
    input  logic        tx_req,
    output logic [31:0] tx_data,
    output logic        tx_valid,
    // modem side
    output logic        rx_m_valid,
    input  logic        rx_m_ready,
    output logic [31:0] rx_m_data,
    input  logic        tx_s_valid,
    output logic        tx_s_ready,
    input  logic [31:0] tx_s_data,
    input  logic        tx_run,
    output logic [15:0] rx_overrun_cnt,
    output logic [15:0] tx_underrun_cnt,
    // SPI
    input  logic [7:0]  spi_div,
    input  logic [5:0]  spi_nbits,
    input  logic        spi_c_valid,
    output logic        spi_c_ready,
    input  logic [31:0] spi_c_data,
    output logic        spi_r_valid,
    input  logic        spi_r_ready,
    output logic [31:0] spi_r_data,
    output logic        sclk,
    output logic        mosi,
    output logic        cs_n,
    input  logic        miso,
    output logic        spi_busy,
    // sequencer
    input  logic [15:0] lines,
    input  logic [15:0] pulses,
    input  logic [15:0] pll_val,
    input  logic [23:0] pin_sel,
    input  logic [5:0]  pin_inv,
    input  logic [3:0]  hop_sel,
    input  logic [5:0]  safe_val,
    input  logic        force_safe,
    output logic [5:0]  pin,
    output logic        hop_trig,
    output logic [3:0]  profile
);
  rx_path #(.AW(AW)) u_rx (
      .clk(clk), .rst_n(rst_n), .rx_clk(rx_clk), .rx_rst_n(rx_rst_n), .rx_valid(rx_valid), .rx_data(rx_data),
      .m_axis_valid(rx_m_valid), .m_axis_ready(rx_m_ready), .m_axis_data(rx_m_data), .rx_overrun_cnt(rx_overrun_cnt));
  tx_path #(.AW(AW)) u_tx (
      .clk(clk), .rst_n(rst_n), .s_axis_valid(tx_s_valid), .s_axis_ready(tx_s_ready), .s_axis_data(tx_s_data), .tx_run(tx_run),
      .tx_clk(tx_clk), .tx_rst_n(tx_rst_n), .tx_req(tx_req), .tx_data(tx_data), .tx_valid(tx_valid), .tx_underrun_cnt(tx_underrun_cnt));
  spi_master u_spi (
      .clk(clk), .rst_n(rst_n), .div(spi_div), .nbits(spi_nbits),
      .s_axis_valid(spi_c_valid), .s_axis_ready(spi_c_ready), .s_axis_data(spi_c_data),
      .m_axis_valid(spi_r_valid), .m_axis_ready(spi_r_ready), .m_axis_data(spi_r_data),
      .sclk(sclk), .mosi(mosi), .cs_n(cs_n), .miso(miso), .busy(spi_busy));
  pin_map u_pins (
      .clk(clk), .rst_n(rst_n), .lines(lines), .pulses(pulses), .pll_val(pll_val), .sel(pin_sel), .inv(pin_inv),
      .hop_sel(hop_sel), .safe_val(safe_val), .force_safe(force_safe), .pin(pin), .hop_trig(hop_trig), .profile(profile));
endmodule
