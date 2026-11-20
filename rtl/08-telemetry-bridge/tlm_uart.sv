// tlm_uart - flight-controller UART bridge: uart_rx -> fifo -> tlm_framer (uplink), uart_tx (downlink).
module tlm_uart (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] div,
    input  logic [1:0]  proto,
    input  logic [7:0]  idle_bits,
    input  logic [8:0]  max_len,

    input  logic        rxd,
    output logic        txd,

    output logic        m_axis_valid,     // frames towards the radio
    input  logic        m_axis_ready,
    output logic [7:0]  m_axis_data,
    output logic        m_axis_last,
    output logic        m_axis_err,

    input  logic        s_axis_valid,     // bytes from the radio towards the UART
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,

    output logic        rx_frame_err,
    output logic        rx_overflow,
    output logic        drop
);
  logic       rx_v;
  logic [7:0] rx_d;
  uart_rx u_rx (.clk(clk), .rst_n(rst_n), .div(div), .rxd(rxd),
                .m_axis_valid(rx_v), .m_axis_data(rx_d), .frame_err(rx_frame_err));

  logic       f_v, f_r, f_l;
  logic [7:0] f_d;
  logic       fifo_ready;
  logic [4:0] unused_level;
  axis_fifo #(.W(8), .DEPTH(16)) u_fifo (
      .clk(clk), .rst_n(rst_n),
      .s_axis_valid(rx_v), .s_axis_ready(fifo_ready), .s_axis_data(rx_d), .s_axis_last(1'b0),
      .m_axis_valid(f_v), .m_axis_ready(f_r), .m_axis_data(f_d), .m_axis_last(f_l),
      .level(unused_level));

  always_ff @(posedge clk) begin
    if (!rst_n) rx_overflow <= 1'b0;
    else rx_overflow <= rx_v & ~fifo_ready;
  end

  tlm_framer u_framer (
      .clk(clk), .rst_n(rst_n), .div(div), .proto(proto), .idle_bits(idle_bits), .max_len(max_len),
      .s_axis_valid(f_v), .s_axis_ready(f_r), .s_axis_data(f_d),
      .m_axis_valid(m_axis_valid), .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data),
      .m_axis_last(m_axis_last), .m_axis_err(m_axis_err), .drop(drop));

  logic tx_busy;
  uart_tx u_tx (.clk(clk), .rst_n(rst_n), .div(div),
                .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready), .s_axis_data(s_axis_data),
                .txd(txd), .busy(tx_busy));

  wire unused_ok = &{1'b0, f_l, unused_level, tx_busy};
endmodule
