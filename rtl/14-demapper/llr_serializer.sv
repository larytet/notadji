// llr_serializer - one beat of up to eight LLRs to an 8-bit LLR stream (design/14-demapper.md section 3).
module llr_serializer (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [63:0] s_axis_data,
    input  logic [3:0]  s_nbits,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [7:0]  m_axis_data,
    output logic        m_axis_last
);
  logic [2:0] idx;
  wire [3:0] nb = (s_nbits == 4'd0) ? 4'd1 : s_nbits;
  wire last_llr = ({1'b0, idx} == nb - 4'd1);

  assign m_axis_valid = s_axis_valid;
  assign m_axis_data  = s_axis_data[8*idx +: 8];
  assign m_axis_last  = s_axis_last & last_llr;
  assign s_axis_ready = m_axis_ready & last_llr;

  always_ff @(posedge clk) begin
    if (!rst_n) idx <= '0;
    else if (s_axis_valid & m_axis_ready) idx <= last_llr ? 3'd0 : idx + 3'd1;
  end
endmodule
