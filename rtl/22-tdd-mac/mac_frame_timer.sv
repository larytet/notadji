// mac_frame_timer - TDD frame counter and slot windows for the air unit (master) and the ground unit (follower).
// See design/22-tdd-mac.md section 2.1.
module mac_frame_timer (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        role,              // 0 air unit, 1 ground unit
    input  logic [23:0] frame_ticks,
    input  logic [23:0] dl_ticks,
    input  logic [23:0] ul_start,
    input  logic [23:0] ul_ticks,
    input  logic [15:0] turn_ticks,
    input  logic [23:0] ta_ticks,
    input  logic [23:0] sync_pos,
    input  logic [3:0]  miss_limit,
    input  logic        sync_valid,
    output logic        frame_start,
    output logic [15:0] frame_no,
    output logic [23:0] cnt,
    output logic        tx_en,
    output logic        rx_en,
    output logic        ul_win,
    output logic signed [24:0] sync_err,
    output logic        link_lost,
    output logic        cfg_err
);
  logic [3:0] miss;
  logic       seen;
  wire        wrap = (cnt + 24'd1 >= frame_ticks);       // also true for frame_ticks = 0 or 1
  wire [23:0] half = frame_ticks >> 1;

  // slip between the counter and the expected position at a synchronisation event, modulo the frame
  wire signed [25:0] d0   = $signed({2'b00, cnt}) - $signed({2'b00, sync_pos});
  wire signed [25:0] fsx  = $signed({2'b00, frame_ticks});
  wire signed [25:0] hsx  = $signed({2'b00, half});
  wire signed [25:0] d1   = (d0 >= hsx) ? d0 - fsx : (d0 < -hsx) ? d0 + fsx : d0;
  wire early = (cnt >= half) && (frame_ticks != 24'd0);   // the event belongs to the next frame

  // windows
  wire [24:0] cnt25 = {1'b0, cnt};
  wire [24:0] u_eff = role ? ({1'b0, ul_start} - {1'b0, ta_ticks}) : {1'b0, ul_start};
  wire        ta_ok = !role || (ta_ticks <= ul_start);
  wire        ul_in = ta_ok && (ul_ticks != 24'd0) && (cnt25 >= u_eff) && (cnt25 < u_eff + {1'b0, ul_ticks});
  wire        dl_in = (cnt < dl_ticks);
  wire unused_ok = &{1'b0, d1[25]};
  assign ul_win = ul_in;
  assign tx_en  = role ? ul_in : dl_in;
  assign rx_en  = role ? dl_in : ul_in;

  // configuration check
  wire [24:0] dl_t = {1'b0, dl_ticks} + {9'd0, turn_ticks};
  wire        bad_gu = !ta_ok || (u_eff < dl_t);
  wire        bad_au = ({1'b0, ul_start} < dl_t) || ((ul_ticks != 24'd0) && ({1'b0, ul_start} + {1'b0, ul_ticks} + {9'd0, turn_ticks} > {1'b0, frame_ticks}));
  wire        bad    = (frame_ticks == 24'd0) || (role ? (ul_ticks != 24'd0 && bad_gu) : bad_au);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      cnt         <= '0;
      frame_no    <= '0;
      frame_start <= 1'b0;
      miss        <= '0;
      seen        <= 1'b0;
      link_lost   <= 1'b0;
      sync_err    <= '0;
      cfg_err     <= 1'b0;
    end else begin
      frame_start <= 1'b0;
      cfg_err     <= bad;
      if (role && sync_valid) begin
        cnt       <= sync_pos + 24'd1;
        sync_err  <= d1[24:0];
        miss      <= '0;
        seen      <= 1'b1;
        link_lost <= 1'b0;
        if (early) begin
          frame_no    <= frame_no + 16'd1;
          frame_start <= 1'b1;
        end
      end else if (wrap) begin
        cnt         <= '0;
        frame_no    <= frame_no + 16'd1;
        frame_start <= 1'b1;
        seen        <= 1'b0;
        if (role) begin
          if (seen) miss <= '0;
          else begin
            if (miss != 4'd15) miss <= miss + 4'd1;
            if (miss_limit != 4'd0 && (miss + 4'd1) >= miss_limit) link_lost <= 1'b1;
          end
        end
      end else begin
        cnt <= cnt + 24'd1;
      end
    end
  end
endmodule
