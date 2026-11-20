// mac_sched - slot plan from the round-trip delay (design/22-tdd-mac.md section 2.2).
module mac_sched #(
    parameter int TPU = 200                 // ticks per microsecond
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [23:0] rtt_ticks,
    input  logic        update,
    input  logic [15:0] turn_ticks,
    output logic [23:0] frame_ticks,
    output logic [23:0] dl_ticks,
    output logic [23:0] ul_start,
    output logic [23:0] ul_ticks,
    output logic [23:0] guard_ticks,
    output logic [1:0]  cls
);
  localparam int THR0 = 467 * TPU / 10;     // 46.7 us: 7 km round trip
  localparam int THR1 = 1001 * TPU / 10;    // 100.1 us: 15 km round trip
  localparam int HYS  = 2 * TPU;

  wire [25:0] r = {2'b00, rtt_ticks};
  logic [1:0] ncls;
  always_comb begin
    ncls = cls;
    case (cls)
      2'd0: if (r > 26'(THR0 + HYS)) ncls = (r > 26'(THR1 + HYS)) ? 2'd2 : 2'd1;
      2'd1: begin
        if (r > 26'(THR1 + HYS)) ncls = 2'd2;
        else if (r + 26'(HYS) < 26'(THR0)) ncls = 2'd0;
      end
      default: if (r + 26'(HYS) < 26'(THR1)) ncls = (r + 26'(HYS) < 26'(THR0)) ? 2'd0 : 2'd1;
    endcase
  end

  logic [23:0] f, u;
  always_comb begin
    case (ncls)
      2'd0: begin f = 24'(1000 * TPU); u = 24'(95 * TPU); end
      2'd1: begin f = 24'(2000 * TPU); u = 24'(150 * TPU); end
      default: begin f = 24'(4000 * TPU); u = 24'(272 * TPU); end
    endcase
  end
  wire [24:0] g  = {1'b0, rtt_ticks} + {8'd0, turn_ticks, 1'b0};    // R + 2 turn
  wire [24:0] us = {1'b0, f} - {1'b0, u} - {9'd0, turn_ticks};       // U = F - UL - turn
  wire [24:0] dl = (us > g) ? us - g : 25'd0;

  wire unused_ok = &{1'b0, dl[24], g[24]};
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      cls         <= '0;
      frame_ticks <= '0;
      dl_ticks    <= '0;
      ul_start    <= '0;
      ul_ticks    <= '0;
      guard_ticks <= '0;
    end else if (update) begin
      cls         <= ncls;
      frame_ticks <= f;
      ul_ticks    <= u;
      guard_ticks <= g[23:0];
      ul_start    <= us[23:0];
      dl_ticks    <= dl[23:0];
    end
  end
endmodule
