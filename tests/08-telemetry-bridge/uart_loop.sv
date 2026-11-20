// Test-only wrapper: uart_tx output wired to uart_rx input (T8-04).
module uart_loop (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] div,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,
    output logic        m_axis_valid,
    output logic [7:0]  m_axis_data,
    output logic        frame_err
);
  logic line, busy;
  uart_tx u_tx (.clk(clk), .rst_n(rst_n), .div(div), .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready),
                .s_axis_data(s_axis_data), .txd(line), .busy(busy));
  uart_rx u_rx (.clk(clk), .rst_n(rst_n), .div(div), .rxd(line), .m_axis_valid(m_axis_valid),
                .m_axis_data(m_axis_data), .frame_err(frame_err));
  wire unused_ok = &{1'b0, busy};
endmodule
