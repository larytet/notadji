// pi_steer - proportional-integral steering of the display pixel clock (design/27-display-sync.md section 1.3).
module pi_steer (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        en,
    input  logic        hold,
    input  logic        err_valid,
    input  logic signed [23:0] err,
    input  logic signed [15:0] kp,                 // Q16: 0.1 ppm per clock of error
    input  logic signed [15:0] ki,                 // Q24: 0.1 ppm per clock of error, per update
    input  logic [11:0] ppm_max,                   // 0.1 ppm units
    input  logic [7:0]  slew_max,
    input  logic        preset_valid,
    input  logic signed [15:0] preset,
    output logic signed [15:0] ctl,
    output logic        ctl_valid
);
  logic signed [55:0] acc;
  wire signed [55:0] lim = $signed({44'd0, ppm_max}) <<< 24;
  wire signed [55:0] acc_raw = acc + 56'(err * ki);
  wire signed [55:0] acc_n = (acc_raw > lim) ? lim : (acc_raw < -lim) ? -lim : acc_raw;
  wire signed [39:0] pterm = 40'(err * kp) >>> 16;
  wire signed [39:0] iterm = 40'(acc_n >>> 24);
  wire signed [40:0] u0 = 41'(pterm) + 41'(iterm);
  wire signed [40:0] pm = $signed({29'd0, ppm_max});
  wire signed [40:0] u = (u0 > pm) ? pm : (u0 < -pm) ? -pm : u0;
  wire signed [40:0] dlt = u - 41'(ctl);
  wire signed [40:0] sl = $signed({33'd0, slew_max});
  wire signed [40:0] un = (dlt > sl) ? 41'(ctl) + sl : (dlt < -sl) ? 41'(ctl) - sl : u;
  wire signed [40:0] pre_c = (41'(preset) > pm) ? pm : (41'(preset) < -pm) ? -pm : 41'(preset);

  wire unused_ok = &{1'b0, un[40:16]};
  always_ff @(posedge clk) begin
    if (!rst_n || !en) begin
      acc <= '0;
      ctl <= '0;
      ctl_valid <= 1'b0;
    end else begin
      ctl_valid <= 1'b0;
      if (preset_valid) begin
        acc <= 56'(pre_c) <<< 24;
        ctl <= pre_c[15:0];
      end else if (err_valid && !hold) begin
        acc <= acc_n;
        ctl <= un[15:0];
        ctl_valid <= 1'b1;
      end
    end
  end
endmodule
