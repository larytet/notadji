// msg_bits_pack - bit stream to K-bit message words, zero padding of the last codeword (design/16-tx-chain.md section 2).
module msg_bits_pack (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [10:0] k_bits,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic        s_data,
    input  logic        s_last,          // last bit of the frame
    output logic        m_valid,
    input  logic        m_ready,
    output logic [31:0] m_data,
    output logic        m_last,          // last word of a codeword
    output logic        m_frame_last     // with m_last: final codeword of the frame
);
  logic [10:0] bcnt;
  logic [31:0] acc;
  logic        ended;                    // input frame finished, padding with zero bits
  logic        o_v, o_l, o_fl;
  logic [31:0] o_d;

  wire can_out  = ~o_v | m_ready;
  wire step     = can_out & (ended | s_valid);
  wire bit_in   = ended ? 1'b0 : s_data;
  wire end_now  = ended | (s_valid & s_last);
  wire last_cw  = (bcnt == k_bits - 11'd1);
  wire word_end = (bcnt[4:0] == 5'd31) | last_cw;
  wire [31:0] acc2 = acc | ({31'd0, bit_in} << bcnt[4:0]);

  assign s_ready      = can_out & ~ended;
  assign m_valid      = o_v;
  assign m_data       = o_d;
  assign m_last       = o_l;
  assign m_frame_last = o_fl;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      bcnt  <= '0;
      acc   <= '0;
      ended <= 1'b0;
      o_v   <= 1'b0;
    end else begin
      if (o_v && m_ready) o_v <= 1'b0;
      if (step) begin
        if (word_end) begin
          o_v  <= 1'b1;
          o_d  <= acc2;
          o_l  <= last_cw;
          o_fl <= last_cw & end_now;
          acc  <= 32'd0;
        end else acc <= acc2;
        if (last_cw) begin
          bcnt  <= '0;
          ended <= 1'b0;
        end else begin
          bcnt  <= bcnt + 11'd1;
          if (end_now) ended <= 1'b1;
        end
      end
    end
  end
endmodule
