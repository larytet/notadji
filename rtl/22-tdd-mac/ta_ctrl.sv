// ta_ctrl - timing-advance loop in the ground unit (design/22-tdd-mac.md section 2.3).
module ta_ctrl #(
    parameter int RES = 20,                 // quantisation step in ticks (0.1 us at 200 MHz)
    parameter int TPU = 200                 // ticks per microsecond
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        meas_valid,
    input  logic signed [23:0] meas_err,    // arrival late (+) or early (-) relative to the plan, ticks
    input  logic        ta_set_valid,
    input  logic [23:0] ta_set,
    input  logic [23:0] ta_max,
    output logic [23:0] ta_ticks,
    output logic [19:0] range_dm
);
  // range in decimetres: one-way distance per tick of round-trip delay = c / (2 TPU) = 1499 / TPU dm, as a x1024 fixed-point factor
  localparam int RM = 1499 * 1024 / TPU;
  wire [41:0] rng = {18'd0, ta_ticks} * 42'(RM);
  wire signed [26:0] t0 = $signed({3'b000, ta_ticks}) + 27'(meas_err);
  wire signed [26:0] tr = (t0 + 27'(RES / 2)) / 27'(RES);     // round to the nearest step (t0 >= 0 after the clamp below)
  wire signed [26:0] tq = (t0 <= 0) ? 27'sd0 : tr * 27'(RES);
  wire signed [26:0] tm = $signed({3'b000, ta_max});
  wire signed [26:0] tc = (tq > tm) ? tm : tq;

  wire unused_ok = &{1'b0, tc[26:24], rng[41:30], rng[9:0]};
  always_ff @(posedge clk) begin
    if (!rst_n) ta_ticks <= '0;
    else if (ta_set_valid) ta_ticks <= (ta_set > ta_max) ? ta_max : ta_set;
    else if (meas_valid) ta_ticks <= tc[23:0];
  end

  assign range_dm = rng[29:10];
endmodule
