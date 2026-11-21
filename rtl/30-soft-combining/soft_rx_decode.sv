// Module 30: combiner followed by the decoder array; result feedback closes the loop.
module soft_rx_decode #(
    parameter int P     = 1,
    parameter int DEPTH = 8,
    parameter int PEND  = 8
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        mode,
    input  logic [2:0]  code,
    input  logic [5:0]  max_iter,
    input  logic [15:0] key_seq,
    input  logic [7:0]  key_cw,
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
    output logic        err_len,
    input  logic        drop_seq_valid,
    input  logic [15:0] drop_seq,
    input  logic        drop_all,
    output logic [15:0] n_hit,
    output logic [15:0] n_miss,
    output logic [15:0] n_evict,
    output logic [15:0] n_ovf,
    output logic [$clog2(DEPTH+1)-1:0] occupancy
);
  logic        c_valid, c_ready, c_last;
  logic signed [7:0] c_data;
  logic [2:0]  c_code;
  logic [5:0]  c_mi;
  logic        first_q;      // next output word is the first of a codeword
  wire         res_valid = m_axis_valid & m_axis_ready & first_q;

  llr_combiner #(.DEPTH(DEPTH), .PEND(PEND)) u_comb (
      .clk(clk), .rst_n(rst_n), .mode(mode), .code(code), .key_seq(key_seq), .key_cw(key_cw), .maxit(max_iter),
      .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready), .s_axis_data(s_axis_data), .s_axis_last(s_axis_last),
      .m_axis_valid(c_valid), .m_axis_ready(c_ready), .m_axis_data(c_data), .m_axis_last(c_last),
      .m_code(c_code), .m_maxit(c_mi),
      .res_valid(res_valid), .res_ok(m_ok),
      .drop_seq_valid(drop_seq_valid), .drop_seq(drop_seq), .drop_all(drop_all),
      .n_hit(n_hit), .n_miss(n_miss), .n_evict(n_evict), .n_ovf(n_ovf), .occupancy(occupancy));

  ldpc_dec_array #(.P(P)) u_arr (
      .clk(clk), .rst_n(rst_n), .code(c_code), .max_iter(c_mi),
      .s_axis_valid(c_valid), .s_axis_ready(c_ready), .s_axis_data(c_data), .s_axis_last(c_last),
      .m_axis_valid(m_axis_valid), .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data), .m_axis_last(m_axis_last),
      .m_ok(m_ok), .m_iters(m_iters), .err_len(err_len));

  always_ff @(posedge clk) begin
    if (!rst_n) first_q <= 1'b1;
    else if (m_axis_valid && m_axis_ready) first_q <= m_axis_last;
  end
endmodule
