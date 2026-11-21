// Module 30: array of P LDPC decoders (module 20); codewords dealt round-robin, results merged in order.
module ldpc_dec_array #(
    parameter int P = 2
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [2:0]  code,
    input  logic [5:0]  max_iter,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic signed [7:0] s_axis_data,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic        m_axis_last,
    output logic        m_ok,
    output logic [5:0]  m_iters,
    output logic        err_len
);
  localparam int W = (P > 1) ? $clog2(P) : 1;
  logic [W-1:0] in_sel, out_sel;
  logic [P-1:0] i_valid, i_ready, o_valid, o_last, o_ok_unused, i_err;
  logic [31:0]  o_data [P];
  logic         o_okv [P];
  logic [5:0]   o_it [P];
  logic [P-1:0] o_ready;

  genvar g;
  generate
    for (g = 0; g < P; g++) begin : gi
      ldpc_dec u_dec (
          .clk(clk), .rst_n(rst_n), .code(code), .max_iter(max_iter),
          .s_axis_valid(i_valid[g]), .s_axis_ready(i_ready[g]), .s_axis_data(s_axis_data), .s_axis_last(s_axis_last),
          .m_axis_valid(o_valid[g]), .m_axis_ready(o_ready[g]), .m_axis_data(o_data[g]), .m_axis_last(o_last[g]),
          .m_ok(o_okv[g]), .m_iters(o_it[g]), .err_len(i_err[g]));
      assign i_valid[g] = s_axis_valid & (in_sel == W'(g));
      assign o_ready[g] = m_axis_ready & (out_sel == W'(g));
    end
  endgenerate

  assign s_axis_ready = i_ready[in_sel];
  assign m_axis_valid = o_valid[out_sel];
  assign m_axis_data  = o_data[out_sel];
  assign m_axis_last  = o_last[out_sel];
  assign m_ok         = o_okv[out_sel];
  assign m_iters      = o_it[out_sel];
  assign err_len      = |i_err;
  assign o_ok_unused  = '0;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      in_sel  <= '0;
      out_sel <= '0;
    end else begin
      if (s_axis_valid && s_axis_ready && s_axis_last) in_sel <= (in_sel == W'(P - 1)) ? '0 : in_sel + W'(1);
      if (m_axis_valid && m_axis_ready && m_axis_last) out_sel <= (out_sel == W'(P - 1)) ? '0 : out_sel + W'(1);
    end
  end
endmodule
