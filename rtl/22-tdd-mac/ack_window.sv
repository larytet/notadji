// ack_window - last-64-slices reception bitmap for the uplink feedback (design/22-tdd-mac.md section 2.4).
module ack_window (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        ev_valid,
    input  logic [15:0] ev_seq,
    input  logic        ev_ok,
    input  logic        fb_req,
    output logic        fb_valid,
    output logic [15:0] fb_hi,
    output logic [63:0] fb_bits,
    output logic [15:0] late_cnt
);
  logic [15:0] hi;
  logic [63:0] bits;
  logic        have;
  wire signed [15:0] diff = $signed(ev_seq - hi);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      hi       <= '0;
      bits     <= '0;
      have     <= 1'b0;
      late_cnt <= '0;
      fb_valid <= 1'b0;
      fb_hi    <= '0;
      fb_bits  <= '0;
    end else begin
      fb_valid <= fb_req;
      if (fb_req) begin
        fb_hi   <= hi;
        fb_bits <= bits;
      end
      if (ev_valid) begin
        if (!have) begin
          have <= 1'b1;
          hi   <= ev_seq;
          bits <= {ev_ok, 63'd0};
        end else if (diff > 0) begin
          hi   <= ev_seq;
          bits <= ((diff >= 64) ? 64'd0 : (bits >> diff[5:0])) | (ev_ok ? 64'h8000_0000_0000_0000 : 64'd0);
        end else if (diff < -63) begin
          late_cnt <= late_cnt + 16'd1;
        end else if (ev_ok) begin
          bits[6'd63 + diff[5:0]] <= 1'b1;
        end
      end
    end
  end
endmodule
