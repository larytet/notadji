// cfr_chain - two clip-and-filter passes (design/26-papr-dpd.md section 1.2).
module cfr_chain (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [1:0]  wr_en,
    input  logic [7:0]  wr_idx,
    input  logic [15:0] wr_g,
    input  logic        s_valid,
    input  logic [31:0] s_data,
    output logic        m_valid,
    output logic [31:0] m_data
);
  logic v1, v2, v3;
  logic [31:0] d1, d2, d3;
  cfr_clip u_c1 (.clk(clk), .rst_n(rst_n), .wr_en(wr_en[0]), .wr_idx(wr_idx), .wr_g(wr_g), .s_valid(s_valid), .s_data(s_data), .m_valid(v1), .m_data(d1));
  cfr_fir  u_f1 (.clk(clk), .rst_n(rst_n), .s_valid(v1), .s_data(d1), .m_valid(v2), .m_data(d2));
  cfr_clip u_c2 (.clk(clk), .rst_n(rst_n), .wr_en(wr_en[1]), .wr_idx(wr_idx), .wr_g(wr_g), .s_valid(v2), .s_data(d2), .m_valid(v3), .m_data(d3));
  cfr_fir  u_f2 (.clk(clk), .rst_n(rst_n), .s_valid(v3), .s_data(d3), .m_valid(m_valid), .m_data(m_data));
endmodule
