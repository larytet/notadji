// pin_map - sequencer lines to transceiver control pins, with a hardware fault override (design/11-radio-interface.md section 4).
module pin_map (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] lines,
    input  logic [15:0] pulses,
    input  logic [15:0] pll_val,
    input  logic [23:0] sel,         // six 4-bit line selectors
    input  logic [5:0]  inv,
    input  logic [3:0]  hop_sel,
    input  logic [5:0]  safe_val,
    input  logic        force_safe,
    output logic [5:0]  pin,
    output logic        hop_trig,
    output logic [3:0]  profile
);
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      pin      <= 6'd0;
      hop_trig <= 1'b0;
      profile  <= 4'd0;
    end else begin
      for (int k = 0; k < 6; k++) pin[k] <= force_safe ? safe_val[k] : (lines[sel[4*k+:4]] ^ inv[k]);
      hop_trig <= force_safe ? 1'b0 : pulses[hop_sel];
      profile  <= pll_val[3:0];
    end
  end

  wire unused_ok = &{1'b0, pll_val[15:4]};
endmodule
