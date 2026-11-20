// Test-only wrapper: cp_insert followed by cp_remove (backoff 0), used by T4-10.
module cp_loop #(
    parameter int W        = 32,
    parameter int MAX_LOG2 = 9
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [3:0]   fft_log2,
    input  logic [1:0]   cp_sel,
    input  logic         s_axis_valid,
    output logic         s_axis_ready,
    input  logic [W-1:0] s_axis_data,
    input  logic         s_axis_last,
    output logic         m_axis_valid,
    input  logic         m_axis_ready,
    output logic [W-1:0] m_axis_data,
    output logic         m_axis_last,
    output logic         err_len
);
  logic         v, r, l, e0, e1;
  logic [W-1:0] d;
  cp_insert #(.W(W), .MAX_LOG2(MAX_LOG2)) u_ins (
      .clk(clk), .rst_n(rst_n), .fft_log2(fft_log2), .cp_sel(cp_sel),
      .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready), .s_axis_data(s_axis_data), .s_axis_last(s_axis_last),
      .m_axis_valid(v), .m_axis_ready(r), .m_axis_data(d), .m_axis_last(l), .err_len(e0));
  cp_remove #(.W(W), .MAX_LOG2(MAX_LOG2)) u_rem (
      .clk(clk), .rst_n(rst_n), .fft_log2(fft_log2), .cp_sel(cp_sel), .backoff('0),
      .s_axis_valid(v), .s_axis_ready(r), .s_axis_data(d), .s_axis_last(l),
      .m_axis_valid(m_axis_valid), .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data), .m_axis_last(m_axis_last),
      .err_len(e1));
  assign err_len = e0 | e1;
endmodule
