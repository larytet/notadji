// rx_path - radio-clock samples to the system clock with overrun accounting (design/11-radio-interface.md section 2).
module rx_path #(
    parameter int AW = 4
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        rx_clk,
    input  logic        rx_rst_n,
    input  logic        rx_valid,
    input  logic [31:0] rx_data,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic [15:0] rx_overrun_cnt
);
  logic f_ready, f_last;
  axis_cdc_fifo #(.W(32), .AW(AW)) u_fifo (
      .s_clk(rx_clk), .s_rst_n(rx_rst_n), .s_axis_valid(rx_valid), .s_axis_ready(f_ready), .s_axis_data(rx_data), .s_axis_last(1'b0),
      .m_clk(clk), .m_rst_n(rst_n), .m_axis_valid(m_axis_valid), .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data), .m_axis_last(f_last));

  gray_cnt_sync u_cnt (
      .src_clk(rx_clk), .src_rst_n(rx_rst_n), .inc(rx_valid & ~f_ready),
      .dst_clk(clk), .dst_rst_n(rst_n), .cnt_dst(rx_overrun_cnt));

  wire unused_ok = &{1'b0, f_last};
endmodule
