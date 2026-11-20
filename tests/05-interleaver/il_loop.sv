// Test-only wrapper: interleaver followed by de-interleaver with the same block length (T5-04).
module il_loop #(
    parameter int W     = 1,
    parameter int MAX_N = 1024
) (
    input  logic                       clk,
    input  logic                       rst_n,
    input  logic [$clog2(MAX_N+1)-1:0] n,
    input  logic                       s_axis_valid,
    output logic                       s_axis_ready,
    input  logic [W-1:0]               s_axis_data,
    input  logic                       s_axis_last,
    output logic                       m_axis_valid,
    input  logic                       m_axis_ready,
    output logic [W-1:0]               m_axis_data,
    output logic                       m_axis_last,
    output logic                       err_len
);
  logic         v, r, l, e0, e1;
  logic [$clog2(MAX_N+1)-1:0] n0, n1;
  logic [W-1:0] d;
  block_interleaver #(.W(W), .MAX_N(MAX_N), .DEINT(1'b0)) u_i (
      .clk(clk), .rst_n(rst_n), .n(n),
      .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready), .s_axis_data(s_axis_data), .s_axis_last(s_axis_last),
      .m_axis_valid(v), .m_axis_ready(r), .m_axis_data(d), .m_axis_last(l), .m_n(n0), .err_len(e0));
  block_interleaver #(.W(W), .MAX_N(MAX_N), .DEINT(1'b1)) u_d (
      .clk(clk), .rst_n(rst_n), .n(n0),
      .s_axis_valid(v), .s_axis_ready(r), .s_axis_data(d), .s_axis_last(l),
      .m_axis_valid(m_axis_valid), .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data), .m_axis_last(m_axis_last), .m_n(n1),
      .err_len(e1));
  assign err_len = e0 | e1;
  wire unused_ok = &{1'b0, n1};
endmodule
