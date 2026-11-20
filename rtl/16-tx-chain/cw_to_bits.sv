// cw_to_bits - codeword words to a bit stream, N bits per codeword (design/16-tx-chain.md section 2).
module cw_to_bits (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [10:0] n_bits,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [31:0] s_data,
    input  logic        s_last,          // last word of a codeword (the bit count decides the end; kept for the stream convention)
    input  logic        s_fl,            // valid with the word taken (frame-final codeword flag)
    output logic        m_valid,
    input  logic        m_ready,
    output logic        m_data,
    output logic        m_last,          // last bit of a codeword
    output logic        m_fl             // with m_last: final codeword of the frame
);
  logic [31:0] w;
  logic        have, fl_q;
  logic [4:0]  bidx;
  logic [10:0] cnt;

  assign s_ready = ~have;
  assign m_valid = have;
  assign m_data  = w[bidx];
  assign m_last  = (cnt == n_bits - 11'd1);
  assign m_fl    = fl_q & m_last;

  wire m_xfer = have & m_ready;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      have <= 1'b0;
      cnt  <= '0;
      bidx <= '0;
    end else begin
      if (s_valid && !have) begin
        w    <= s_data;
        fl_q <= s_fl;
        have <= 1'b1;
        bidx <= '0;
      end
      if (m_xfer) begin
        cnt  <= m_last ? 11'd0 : cnt + 11'd1;
        bidx <= bidx + 5'd1;
        if (bidx == 5'd31 || m_last) have <= 1'b0;
      end
    end
  end
  wire unused_ok = &{1'b0, s_last};
endmodule
