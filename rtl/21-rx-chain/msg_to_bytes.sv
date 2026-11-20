// msg_to_bytes - decoded message bits to payload bytes, trimmed to nbytes (design/21-rx-chain.md section 1).
module msg_to_bytes (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] nbytes,
    input  logic [7:0]  ncw,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic        s_data,            // one message bit per beat, bit 0 first
    input  logic        s_last,            // last bit of a codeword's message
    output logic        m_valid,
    input  logic        m_ready,
    output logic [7:0]  m_data,
    output logic        m_last,
    output logic        frame_done         // one clock after the last bit of the last codeword
);
  logic [2:0]  bi;
  logic [7:0]  acc;
  logic [15:0] bcnt;
  logic [7:0]  cwcnt;
  logic        o_v, o_l;
  logic [7:0]  o_d;
  logic        done_p;

  wire can_out = ~o_v | m_ready;
  wire wr_byte = (bi == 3'd7);
  wire keep    = (bcnt < nbytes);
  // a byte is produced every eighth bit: wait for the output slot only then
  assign s_ready = (wr_byte && keep) ? can_out : 1'b1;
  wire xfer = s_valid & s_ready;
  wire [7:0] acc2 = acc | ({7'd0, s_data} << bi);

  assign m_valid    = o_v;
  assign m_data     = o_d;
  assign m_last     = o_l;
  assign frame_done = done_p;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      bi     <= '0;
      acc    <= '0;
      bcnt   <= '0;
      cwcnt  <= '0;
      o_v    <= 1'b0;
      done_p <= 1'b0;
    end else begin
      done_p <= 1'b0;
      if (o_v && m_ready) o_v <= 1'b0;
      if (xfer) begin
        if (wr_byte) begin
          if (keep) begin
            o_v  <= 1'b1;
            o_d  <= acc2;
            o_l  <= (bcnt == nbytes - 16'd1);
            bcnt <= bcnt + 16'd1;
          end
          acc <= 8'd0;
          bi  <= 3'd0;
        end else begin
          acc <= acc2;
          bi  <= bi + 3'd1;
        end
        if (s_last) begin
          if (cwcnt == ncw - 8'd1) begin
            cwcnt  <= '0;
            bcnt   <= '0;
            bi     <= '0;
            acc    <= '0;
            done_p <= 1'b1;
          end else cwcnt <= cwcnt + 8'd1;
        end
      end
    end
  end
endmodule
