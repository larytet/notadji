// Test-only wrapper: receiver acknowledgement window and transmitter retransmission control side by side.
// The channel and the uplink delay are modelled in the testbench.
module ack_loop (
    input  logic        clk,
    input  logic        rst_n,
    // receiver
    input  logic        ev_valid,
    input  logic [15:0] ev_seq,
    input  logic        ev_ok,
    input  logic        fb_req,
    output logic        r_fb_valid,
    output logic [15:0] r_fb_hi,
    output logic [63:0] r_fb_bits,
    // transmitter
    input  logic [31:0] now,
    input  logic [31:0] tx_ticks,
    input  logic [31:0] owd_ticks,
    input  logic [3:0]  max_retx,
    input  logic [3:0]  holdoff,
    input  logic [31:0] tmo_ticks,
    input  logic        sent_valid,
    input  logic [15:0] sent_seq,
    input  logic [31:0] sent_deadline,
    input  logic        t_fb_valid,
    output logic        t_fb_ready,
    input  logic [15:0] t_fb_hi,
    input  logic [63:0] t_fb_bits,
    output logic        rtx_valid,
    input  logic        rtx_ready,
    output logic [15:0] rtx_seq,
    output logic        rf_valid,
    input  logic        rf_ready,
    output logic [15:0] rf_seq,
    output logic [15:0] drop_cnt,
    output logic [15:0] stale_cnt
);
  logic [15:0] late, ovf;
  logic busy;
  ack_window u_a (.clk(clk), .rst_n(rst_n), .ev_valid(ev_valid), .ev_seq(ev_seq), .ev_ok(ev_ok), .fb_req(fb_req),
      .fb_valid(r_fb_valid), .fb_hi(r_fb_hi), .fb_bits(r_fb_bits), .late_cnt(late));
  retx_ctrl u_r (.clk(clk), .rst_n(rst_n), .now(now), .tx_ticks(tx_ticks), .owd_ticks(owd_ticks), .max_retx(max_retx), .holdoff(holdoff), .tmo_ticks(tmo_ticks),
      .sent_valid(sent_valid), .sent_seq(sent_seq), .sent_deadline(sent_deadline), .fb_valid(t_fb_valid), .fb_ready(t_fb_ready),
      .fb_hi(t_fb_hi), .fb_bits(t_fb_bits), .rtx_valid(rtx_valid), .rtx_ready(rtx_ready), .rtx_seq(rtx_seq), .rf_valid(rf_valid),
      .rf_ready(rf_ready), .rf_seq(rf_seq), .drop_cnt(drop_cnt), .stale_cnt(stale_cnt), .ovf_cnt(ovf), .busy(busy));
  wire unused_ok = &{1'b0, late, ovf, busy};
endmodule
