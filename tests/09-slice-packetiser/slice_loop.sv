// Test-only wrapper: slice_pack followed by slice_unpack (T9-11).
module slice_loop #(
    parameter int MAX_BYTES = 4096
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] meta_frame,
    input  logic [7:0]  meta_idx,
    input  logic [3:0]  meta_flags,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [7:0]  m_axis_data,
    output logic        m_axis_last,
    output logic        st_valid,
    output logic        st_hdr_ok,
    output logic        st_crc_ok,
    output logic        st_trunc,
    output logic [15:0] st_frame,
    output logic [7:0]  st_idx,
    output logic [3:0]  st_flags,
    output logic [15:0] st_len
);
  logic       v, r, l;
  logic [7:0] d;
  slice_pack #(.MAX_BYTES(MAX_BYTES)) u_p (
      .clk(clk), .rst_n(rst_n), .meta_frame(meta_frame), .meta_idx(meta_idx), .meta_flags(meta_flags),
      .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready), .s_axis_data(s_axis_data), .s_axis_last(s_axis_last),
      .m_axis_valid(v), .m_axis_ready(r), .m_axis_data(d), .m_axis_last(l));
  slice_unpack #(.MAX_BYTES(MAX_BYTES)) u_u (
      .clk(clk), .rst_n(rst_n),
      .s_axis_valid(v), .s_axis_ready(r), .s_axis_data(d), .s_axis_last(l),
      .m_axis_valid(m_axis_valid), .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data), .m_axis_last(m_axis_last),
      .st_valid(st_valid), .st_hdr_ok(st_hdr_ok), .st_crc_ok(st_crc_ok), .st_trunc(st_trunc),
      .st_frame(st_frame), .st_idx(st_idx), .st_flags(st_flags), .st_len(st_len));
endmodule
