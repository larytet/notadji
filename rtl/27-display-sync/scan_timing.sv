// scan_timing - programmable video timing generator (design/27-display-sync.md section 1.1).
module scan_timing (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        en,
    input  logic [15:0] h_active, h_fp, h_sync, h_bp,
    input  logic [15:0] v_active, v_fp, v_sync, v_bp,
    input  logic        hs_pol,
    input  logic        vs_pol,
    input  logic signed [7:0] slip,
    output logic        hs,
    output logic        vs,
    output logic        de,
    output logic [15:0] x,
    output logic [15:0] y,
    output logic        line_start,
    output logic        vs_start,
    output logic [15:0] frame_cnt
);
  logic [15:0] hx, vy;
  logic signed [8:0] slip_l;                       // slip in force for this frame

  wire [15:0] h_total = h_active + h_fp + h_sync + h_bp;
  wire [15:0] v_total = v_active + v_fp + v_sync + v_bp;
  wire [15:0] hs_lo   = h_active + h_fp;
  wire [15:0] hs_hi   = h_active + h_fp + h_sync;
  wire [15:0] vs_lo   = v_active + v_fp;
  wire [15:0] vs_hi   = v_active + v_fp + v_sync;

  // the first line of the vertical blanking is the one that carries the slip (at the end of its back porch)
  wire        slip_line = (vy == v_active);
  wire signed [17:0] slip_min = -$signed({2'b00, h_bp}) + 18'sd1;
  wire signed [17:0] slip_in = {{10{slip_l[8]}}, slip_l[7:0]};
  wire signed [17:0] slip_eff = (slip_in < slip_min) ? slip_min : slip_in;
  wire signed [17:0] hlast_s = $signed({2'b00, h_total}) - 18'sd1 + (slip_line ? slip_eff : 18'sd0);
  wire        h_end = ($signed({2'b00, hx}) == hlast_s);
  wire        v_end = (vy == v_total - 16'd1);

  wire in_hs = (hx >= hs_lo) && (hx < hs_hi);
  wire in_vs = (vy >= vs_lo) && (vy < vs_hi);
  assign hs = en & (hs_pol ? in_hs : ~in_hs);
  assign vs = en & (vs_pol ? in_vs : ~in_vs);
  assign de = en & (hx < h_active) & (vy < v_active);
  assign x = hx;
  assign y = vy;
  assign line_start = en & (hx == 16'd0);
  assign vs_start = en & (hx == 16'd0) & (vy == vs_lo);

  always_ff @(posedge clk) begin
    if (!rst_n || !en) begin
      hx <= '0;
      vy <= '0;
      slip_l <= '0;
      frame_cnt <= '0;
    end else begin
      if (hx == 16'd0 && vy == 16'd0) slip_l <= {slip[7], slip};
      if (h_end) begin
        hx <= '0;
        if (v_end) begin
          vy <= '0;
          frame_cnt <= frame_cnt + 16'd1;
        end else vy <= vy + 16'd1;
      end else hx <= hx + 16'd1;
    end
  end
endmodule
