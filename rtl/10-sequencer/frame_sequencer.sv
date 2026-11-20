// frame_sequencer - replays a table of timed events once per frame (design/10-frame-timeline-sequencer.md).
module frame_sequencer #(
    parameter int          DEPTH       = 64,       // power of two, 2 or more
    parameter int          SAFE_PERIOD = 1000,     // frame length before the first commit, clocks
    parameter logic [15:0] SAFE_LINES  = 16'h0000
) (
    input  logic                       clk,
    input  logic                       rst_n,
    input  logic                       run,
    input  logic                       force_safe,
    input  logic                       wr_en,
    input  logic [$clog2(DEPTH)-1:0]   wr_addr,
    input  logic [47:0]                wr_data,     // {time[23:0], action[7:0], arg[15:0]}
    input  logic                       commit,
    output logic [15:0]                lines,
    output logic [15:0]                pulses,
    output logic [15:0]                gain_val,
    output logic [15:0]                pll_val,
    output logic                       evt_pulse,
    output logic                       frame_start,
    output logic [31:0]                frame_cnt,
    output logic [15:0]                missed,
    output logic                       active_bank,
    output logic                       pending,
    output logic [23:0]                tick,
    output logic                       forced
);
  localparam int AW        = $clog2(DEPTH);
  localparam logic [23:0] MIN_FRAME = 24'd16;
  localparam logic [7:0]  A_SET = 8'd1, A_CLR = 8'd2, A_PULSE = 8'd3, A_GAIN = 8'd4, A_PLL = 8'd5, A_END = 8'd15;

  logic [47:0] bank0[DEPTH];
  logic [47:0] bank1[DEPTH];
  logic        safe_tbl;          // no table committed yet: run the built-in safe frame
  logic [AW-1:0] rp;
  logic        exhausted;

  // write into the inactive bank only
  always_ff @(posedge clk) begin
    if (wr_en) begin
      if (active_bank) bank0[wr_addr] <= wr_data;
      else bank1[wr_addr] <= wr_data;
    end
  end

  wire [47:0] safe_entry = {24'(SAFE_PERIOD), A_END, 16'h0000};
  wire [47:0] entry      = safe_tbl ? safe_entry : (active_bank ? bank1[rp] : bank0[rp]);
  wire [23:0] e_time     = entry[47:24];
  wire [7:0]  e_act      = entry[23:16];
  wire [15:0] e_arg      = entry[15:0];
  wire        is_end     = (e_act == A_END);
  wire [23:0] t_eff      = (is_end && e_time < MIN_FRAME) ? MIN_FRAME : e_time;
  // END executes in the clock where tick = time - 1, so that the frame is exactly `time` clocks long
  wire [23:0] t_cmp      = is_end ? (t_eff - 24'd1) : t_eff;
  wire        fire       = run & ~exhausted & (tick >= t_cmp);

  logic [15:0] lines_r, pulses_r;

  assign forced = force_safe;
  assign lines  = force_safe ? SAFE_LINES : lines_r;
  assign pulses = force_safe ? 16'h0000 : pulses_r;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      active_bank <= 1'b0;
      pending     <= 1'b0;
      safe_tbl    <= 1'b1;
      rp          <= '0;
      exhausted   <= 1'b0;
      tick        <= '0;
      lines_r     <= '0;
      pulses_r    <= '0;
      gain_val    <= '0;
      pll_val     <= '0;
      evt_pulse   <= 1'b0;
      frame_start <= 1'b1;
      frame_cnt   <= 32'd1;
      missed      <= '0;
    end else begin
      pulses_r    <= '0;
      evt_pulse   <= 1'b0;
      frame_start <= 1'b0;
      if (commit) pending <= 1'b1;
      if (run) tick <= tick + 24'd1;
      if (fire) begin
        if (is_end) begin
          tick        <= '0;
          rp          <= '0;
          exhausted   <= 1'b0;
          lines_r     <= '0;
          frame_start <= 1'b1;
          frame_cnt   <= frame_cnt + 32'd1;
          if (pending) begin
            active_bank <= ~active_bank;
            safe_tbl    <= 1'b0;
            pending     <= commit;      // a commit in this same clock stays pending for the next frame end
            missed      <= '0;
          end else if (missed != 16'hFFFF) begin
            missed <= missed + 16'd1;
          end
        end else begin
          evt_pulse <= 1'b1;
          if (rp == AW'(DEPTH - 1)) exhausted <= 1'b1;
          else rp <= rp + 1'b1;
          case (e_act)
            A_SET:   lines_r <= lines_r | e_arg;
            A_CLR:   lines_r <= lines_r & ~e_arg;
            A_PULSE: pulses_r[e_arg[3:0]] <= 1'b1;
            A_GAIN:  gain_val <= e_arg;
            A_PLL:   pll_val <= e_arg;
            default: ;
          endcase
        end
      end
    end
  end
endmodule
