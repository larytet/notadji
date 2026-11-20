// scrambler - additive LFSR scrambler, own inverse, zero-latency pass-through (design/03-scrambler-crc.md section 3).
module scrambler #(
    parameter int             W    = 32,
    parameter int             LEN  = 7,
    parameter logic [LEN-1:0] TAPS = 7'b1001000,   // x^7 + x^4 + 1 (802.11)
    parameter logic [LEN-1:0] SEED = '1
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         s_axis_valid,
    output logic         s_axis_ready,
    input  logic [W-1:0] s_axis_data,
    input  logic         s_axis_last,
    output logic         m_axis_valid,
    input  logic         m_axis_ready,
    output logic [W-1:0] m_axis_data,
    output logic         m_axis_last
);
  logic [LEN-1:0] state, st_next;
  logic [W-1:0]   ks;

  always_comb begin
    logic [LEN-1:0] s;
    logic           fb;
    s = state;
    ks = '0;
    for (int i = 0; i < W; i++) begin
      fb    = ^(s & TAPS);
      ks[i] = fb;
      s     = {s[LEN-2:0], fb};
    end
    st_next = s;
  end

  assign m_axis_valid = s_axis_valid;
  assign s_axis_ready = m_axis_ready;
  assign m_axis_data  = s_axis_data ^ ks;
  assign m_axis_last  = s_axis_last;

  wire xfer = s_axis_valid & m_axis_ready;

  always_ff @(posedge clk) begin
    if (!rst_n) state <= SEED;
    else if (xfer) state <= s_axis_last ? SEED : st_next;
  end
endmodule
