// axis_skid - register slice with full throughput (design/01-axi-library.md section 3.1).
// s_axis_ready is a registered signal (it does not depend on m_axis_ready in the same cycle).
module axis_skid #(
    parameter int W = 32
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
  logic [W:0] out_d, skid_d;
  logic out_v, skid_v;

  assign s_axis_ready = ~skid_v;
  assign m_axis_valid = out_v;
  assign {m_axis_last, m_axis_data} = out_d;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      out_v  <= 1'b0;
      skid_v <= 1'b0;
    end else if (skid_v) begin
      // output stage is full and a word is parked in the skid register
      if (m_axis_ready) begin
        out_v  <= 1'b1;
        skid_v <= 1'b0;
      end
    end else if (!out_v || m_axis_ready) begin
      // output stage empty or being consumed: take the input directly
      out_v <= s_axis_valid;
    end else if (s_axis_valid) begin
      // output stage full and stalled: park the input word
      skid_v <= 1'b1;
    end
  end

  // data path (no reset)
  always_ff @(posedge clk) begin
    if (skid_v) begin
      if (m_axis_ready) out_d <= skid_d;
    end else if (!out_v || m_axis_ready) begin
      out_d <= {s_axis_last, s_axis_data};
    end else begin
      skid_d <= {s_axis_last, s_axis_data};
    end
  end
endmodule
