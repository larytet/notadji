// phase_meas - latency between the received frame timing and the display frame marker (design/27-display-sync.md section 1.2).
module phase_meas (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [23:0] period,
    input  logic [23:0] target,
    input  logic        rx_fs,
    input  logic        disp_vs,
    output logic signed [23:0] err,
    output logic        err_valid,
    output logic        lost
);
  logic [23:0] c;
  logic [24:0] silent;
  wire signed [25:0] d0 = $signed({2'b00, c}) - $signed({2'b00, target});
  wire signed [25:0] p  = $signed({2'b00, period});
  wire signed [25:0] hp = $signed({3'b000, period[23:1]});
  wire signed [25:0] d1 = (d0 >= hp) ? d0 - p : (d0 < -hp) ? d0 + p : d0;

  wire unused_ok = &{1'b0, d1[25:24]};
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      c <= '0;
      silent <= '0;
      err <= '0;
      err_valid <= 1'b0;
      lost <= 1'b1;
    end else begin
      err_valid <= 1'b0;
      if (rx_fs) begin
        c <= 24'd0;
        silent <= '0;
        lost <= 1'b0;
      end else begin
        c <= (period != 24'd0 && c + 24'd1 >= period) ? 24'd0 : c + 24'd1;
        if (silent[24:1] >= period) lost <= 1'b1;
        else silent <= silent + 25'd1;
      end
      if (disp_vs && period != 24'd0) begin
        err <= d1[23:0];
        err_valid <= 1'b1;
      end
    end
  end
endmodule
