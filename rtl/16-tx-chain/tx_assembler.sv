// tx_assembler - merges the tone plan stream (module 7) with mapper samples (design/16-tx-chain.md section 2).
module tx_assembler (
    input  logic        pg_valid,
    output logic        pg_ready,
    input  logic [33:0] pg_data,       // {type[1:0], Q[15:0], I[15:0]}
    input  logic        pg_last,
    input  logic        mp_valid,
    output logic        mp_ready,
    input  logic [31:0] mp_data,
    output logic        m_valid,
    input  logic        m_ready,
    output logic [31:0] m_data,
    output logic        m_last
);
  wire [1:0] t = pg_data[33:32];
  wire need_map = (t == 2'd1);

  assign m_valid  = pg_valid & (~need_map | mp_valid);
  assign pg_ready = m_ready & (~need_map | mp_valid);
  assign mp_ready = m_ready & pg_valid & need_map;
  assign m_data   = need_map ? mp_data : (t == 2'd2 ? pg_data[31:0] : 32'd0);
  assign m_last   = pg_last;
endmodule
