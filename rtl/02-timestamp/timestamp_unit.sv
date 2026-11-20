// timestamp_unit - free-running 64-bit counter, per-tap latches and a trace stream (design/02-timestamp-unit.md).
module timestamp_unit #(
    parameter int NTAPS       = 16,   // 2 or more
    parameter int TRACE_DEPTH = 64    // power of two, 2 or more
) (
    input  logic                       clk,
    input  logic                       rst_n,

    input  logic [NTAPS-1:0]           tap_evt,
    output logic [63:0]                ts_now,

    input  logic                       load_valid,
    input  logic [63:0]                load_value,
    input  logic                       adj_valid,
    input  logic [31:0]                adj_delta,

    output logic [NTAPS*64-1:0]        tap_ts_flat,
    output logic [NTAPS*16-1:0]        tap_cnt_flat,

    input  logic                       snap_req,
    output logic [63:0]                snap_ts,

    output logic                       m_axis_valid,
    input  logic                       m_axis_ready,
    output logic [63+$clog2(NTAPS):0]  m_axis_data,
    output logic                       m_axis_last,

    output logic [15:0]                trace_drop
);
  localparam int ID_W = $clog2(NTAPS);
  localparam int PC_W = $clog2(NTAPS + 1);

  logic [63:0] cnt;
  assign ts_now = cnt;

  // counter: load > adjust > increment
  always_ff @(posedge clk) begin
    if (!rst_n) cnt <= 64'd0;
    else if (load_valid) cnt <= load_value;
    else if (adj_valid) cnt <= cnt + 64'd1 + {{32{adj_delta[31]}}, adj_delta};
    else cnt <= cnt + 64'd1;
  end

  // snapshot
  always_ff @(posedge clk) begin
    if (!rst_n) snap_ts <= 64'd0;
    else if (snap_req) snap_ts <= cnt;
  end

  // per-tap latch and event counter
  logic [15:0] tap_cnt[NTAPS];
  logic [63:0] tap_ts[NTAPS];

  always_ff @(posedge clk) begin
    for (int i = 0; i < NTAPS; i++) begin
      if (!rst_n) begin
        tap_cnt[i] <= 16'd0;
        tap_ts[i]  <= 64'd0;
      end else if (tap_evt[i]) begin
        tap_cnt[i] <= tap_cnt[i] + 16'd1;
        tap_ts[i]  <= cnt;
      end
    end
  end

  always_comb begin
    for (int i = 0; i < NTAPS; i++) begin
      tap_ts_flat[i*64+:64]  = tap_ts[i];
      tap_cnt_flat[i*16+:16] = tap_cnt[i];
    end
  end

  // trace record: lowest set tap index, one per clock
  logic [ID_W-1:0] first_id;
  logic [PC_W-1:0] pop;
  always_comb begin
    first_id = '0;
    pop      = '0;
    for (int i = NTAPS - 1; i >= 0; i--) begin
      if (tap_evt[i]) first_id = ID_W'(i);
    end
    for (int i = 0; i < NTAPS; i++) begin
      pop = pop + PC_W'(tap_evt[i]);
    end
  end

  wire any_evt = |tap_evt;
  logic fifo_ready;
  wire accepted = any_evt & fifo_ready;
  wire [PC_W-1:0] lost = pop - PC_W'(accepted);

  // trace_drop saturates at 65535
  wire [16:0] drop_sum = {1'b0, trace_drop} + 17'(lost);
  always_ff @(posedge clk) begin
    if (!rst_n) trace_drop <= 16'd0;
    else trace_drop <= drop_sum[16] ? 16'hFFFF : drop_sum[15:0];
  end

  logic [$clog2(TRACE_DEPTH):0] unused_level;
  axis_fifo #(
      .W    (64 + ID_W),
      .DEPTH(TRACE_DEPTH)
  ) u_trace (
      .clk         (clk),
      .rst_n       (rst_n),
      .s_axis_valid(any_evt),
      .s_axis_ready(fifo_ready),
      .s_axis_data ({first_id, cnt}),
      .s_axis_last (1'b1),
      .m_axis_valid(m_axis_valid),
      .m_axis_ready(m_axis_ready),
      .m_axis_data (m_axis_data),
      .m_axis_last (m_axis_last),
      .level       (unused_level)
  );

  wire unused_ok = &{1'b0, unused_level};
endmodule
