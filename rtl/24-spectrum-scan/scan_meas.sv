// scan_meas - energy of one scan dwell (design/24-spectrum-scan.md section 1.1).
module scan_meas (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,
    input  logic [15:0] settle_ticks,         // sample strobes ignored after start
    input  logic [16:0] dwell_ticks,          // sample strobes accumulated (0 counts as 1)
    input  logic        s_valid,
    input  logic [31:0] s_data,               // {Q, I}
    output logic        busy,
    output logic        done,
    output logic [47:0] sum,
    output logic [11:0] lg,
    output logic        sat,
    output logic [15:0] ovr_cnt
);
  typedef enum logic [1:0] {S_IDLE, S_SETTLE, S_ACC} state_t;
  state_t state;
  logic [16:0] cnt;

  wire signed [15:0] si = s_data[15:0];
  wire signed [15:0] sq = s_data[31:16];
  wire signed [31:0] ii = si * si;
  wire signed [31:0] qq = sq * sq;
  wire [32:0] pw = {1'b0, ii} + {1'b0, qq};
  wire [48:0] nsum = {1'b0, sum} + {16'd0, pw};
  wire [16:0] dwell = (dwell_ticks == 17'd0) ? 17'd1 : dwell_ticks;

  assign busy = (state != S_IDLE);

  // Mitchell logarithm: 16 x position of the leading one + the four bits below it
  logic [5:0]  p;
  logic [3:0]  m;
  logic [47:0] sh;
  always_comb begin
    p = 6'd0;
    for (int i = 0; i < 48; i++) if (sum[i]) p = 6'(i);
    sh = sum << (6'd47 - p);                       // leading one moved to bit 47
    m  = (sum == 48'd0) ? 4'd0 : sh[46:43];
  end
  wire unused_ok = &{1'b0, sh[47], sh[42:0]};
  assign lg = (sum == 48'd0) ? 12'd0 : {2'b00, p, 4'd0} + {8'd0, m};

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state   <= S_IDLE;
      cnt     <= '0;
      sum     <= '0;
      done    <= 1'b0;
      sat     <= 1'b0;
      ovr_cnt <= '0;
    end else begin
      done <= 1'b0;
      case (state)
        S_IDLE: begin
          if (start) begin
            sum   <= '0;
            sat   <= 1'b0;
            cnt   <= '0;
            state <= (settle_ticks == 16'd0) ? S_ACC : S_SETTLE;
          end
        end
        S_SETTLE: begin
          if (start) ovr_cnt <= ovr_cnt + 16'd1;
          if (s_valid) begin
            if (cnt + 17'd1 >= {1'b0, settle_ticks}) begin
              cnt   <= '0;
              state <= S_ACC;
            end else cnt <= cnt + 17'd1;
          end
        end
        default: begin
          if (start) ovr_cnt <= ovr_cnt + 16'd1;
          if (s_valid) begin
            sum <= nsum[47:0];
            if (nsum[48]) sat <= 1'b1;
            if (cnt + 17'd1 >= dwell) begin
              done  <= 1'b1;
              state <= S_IDLE;
            end else cnt <= cnt + 17'd1;
          end
        end
      endcase
    end
  end
endmodule
