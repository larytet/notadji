// sym_blocker - bit stream to blocks of Ncbps bits with zero padding at the end of the frame (design/16-tx-chain.md section 2).
module sym_blocker (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [12:0] ncbps,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic        s_data,
    input  logic        s_last,          // last bit of a codeword
    input  logic        s_fl,            // with s_last: final codeword of the frame
    output logic        m_valid,
    input  logic        m_ready,
    output logic        m_data,
    output logic        m_last,          // last bit of a block
    output logic        blk_pulse,       // one clock per completed block
    output logic        blk_fl           // with blk_pulse: final block of the frame
);
  logic [12:0] c;
  logic        ended;
  logic        o_v, o_d, o_l;

  wire can_out  = ~o_v | m_ready;
  wire step     = can_out & (ended | s_valid);
  wire bit_in   = ended ? 1'b0 : s_data;
  wire fin_now  = ended | (s_valid & s_last & s_fl);
  wire blk_end  = (c == ncbps - 13'd1);

  assign s_ready = can_out & ~ended;
  assign m_valid = o_v;
  assign m_data  = o_d;
  assign m_last  = o_l;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      c         <= '0;
      ended     <= 1'b0;
      o_v       <= 1'b0;
      blk_pulse <= 1'b0;
      blk_fl    <= 1'b0;
    end else begin
      blk_pulse <= 1'b0;
      if (o_v && m_ready) o_v <= 1'b0;
      if (step) begin
        o_v <= 1'b1;
        o_d <= bit_in;
        o_l <= blk_end;
        if (blk_end) begin
          c         <= '0;
          ended     <= 1'b0;
          blk_pulse <= 1'b1;
          blk_fl    <= fin_now;
        end else begin
          c <= c + 13'd1;
          if (fin_now) ended <= 1'b1;
        end
      end
    end
  end
endmodule
