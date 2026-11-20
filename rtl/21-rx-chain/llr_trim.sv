// llr_trim - passes the first `total` LLRs of a frame and drops the padding (design/21-rx-chain.md section 1).
module llr_trim (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] total,             // number of LLRs to pass (ncw x N)
    input  logic [10:0] n_cw,              // codeword length N (for the last flag)
    input  logic [23:0] frame_llr,         // all LLRs of the frame including padding: the counters restart after them
    input  logic        clr,               // start of a new frame
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [7:0]  s_data,
    output logic        m_valid,
    input  logic        m_ready,
    output logic [7:0]  m_data,
    output logic        m_last
);
  logic [15:0] cnt;
  logic [10:0] pos;
  logic [23:0] seen;
  wire last_in = (seen == frame_llr - 24'd1);
  wire pass = (cnt < total);

  assign s_ready = pass ? m_ready : 1'b1;
  assign m_valid = s_valid & pass;
  assign m_data  = s_data;
  assign m_last  = (pos == n_cw - 11'd1);

  always_ff @(posedge clk) begin
    if (!rst_n || clr) begin
      cnt <= '0;
      pos <= '0;
      seen <= '0;
    end else if (s_valid && s_ready) begin
      seen <= last_in ? 24'd0 : seen + 24'd1;
      if (last_in) begin
        cnt <= '0;
        pos <= '0;
      end else if (pass) begin
        cnt <= cnt + 16'd1;
        pos <= (pos == n_cw - 11'd1) ? 11'd0 : pos + 11'd1;
      end
    end
  end
endmodule
