// axis_cdc_fifo - asynchronous FIFO, gray-coded pointers (design/01-axi-library.md section 3.4).
// Both resets must be asserted together. Read side is first-word-fall-through.
module axis_cdc_fifo #(
    parameter int W  = 32,
    parameter int AW = 4   // depth 2**AW, AW >= 2
) (
    input  logic         s_clk,
    input  logic         s_rst_n,
    input  logic         s_axis_valid,
    output logic         s_axis_ready,
    input  logic [W-1:0] s_axis_data,
    input  logic         s_axis_last,

    input  logic         m_clk,
    input  logic         m_rst_n,
    output logic         m_axis_valid,
    input  logic         m_axis_ready,
    output logic [W-1:0] m_axis_data,
    output logic         m_axis_last
);
  logic [W:0] mem[2**AW];

  // write domain
  logic [AW:0] wbin, wgray;
  logic [AW:0] rgray_s1, rgray_s2;
  logic        wfull;

  wire         winc       = s_axis_valid & ~wfull;
  wire  [AW:0] wbin_next  = wbin + {{AW{1'b0}}, winc};
  wire  [AW:0] wgray_next = (wbin_next >> 1) ^ wbin_next;
  wire         wfull_next = (wgray_next == {~rgray_s2[AW:AW-1], rgray_s2[AW-2:0]});

  assign s_axis_ready = ~wfull;

  always_ff @(posedge s_clk) begin
    if (!s_rst_n) begin
      wbin     <= '0;
      wgray    <= '0;
      wfull    <= 1'b0;
      rgray_s1 <= '0;
      rgray_s2 <= '0;
    end else begin
      wbin     <= wbin_next;
      wgray    <= wgray_next;
      wfull    <= wfull_next;
      rgray_s1 <= rgray;
      rgray_s2 <= rgray_s1;
    end
  end

  always_ff @(posedge s_clk) begin
    if (winc) mem[wbin[AW-1:0]] <= {s_axis_last, s_axis_data};
  end

  // read domain
  logic [AW:0] rbin, rgray;
  logic [AW:0] wgray_s1, wgray_s2;
  logic        rempty;

  wire         rinc       = m_axis_ready & ~rempty;
  wire  [AW:0] rbin_next  = rbin + {{AW{1'b0}}, rinc};
  wire  [AW:0] rgray_next = (rbin_next >> 1) ^ rbin_next;
  wire         rempty_next = (rgray_next == wgray_s2);

  assign m_axis_valid = ~rempty;
  assign {m_axis_last, m_axis_data} = mem[rbin[AW-1:0]];

  always_ff @(posedge m_clk) begin
    if (!m_rst_n) begin
      rbin     <= '0;
      rgray    <= '0;
      rempty   <= 1'b1;
      wgray_s1 <= '0;
      wgray_s2 <= '0;
    end else begin
      rbin     <= rbin_next;
      rgray    <= rgray_next;
      rempty   <= rempty_next;
      wgray_s1 <= wgray;
      wgray_s2 <= wgray_s1;
    end
  end
endmodule
