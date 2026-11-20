// Test-only wrapper: air-unit timer, ground-unit timer, schedule computation and timing-advance loop.
// The delay line between the units is modelled in the testbench.
module mac_sys #(
    parameter int TPU = 10,
    parameter int RES = 1
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [23:0] rtt_ticks,
    input  logic        sched_update,
    input  logic [15:0] turn_ticks,
    input  logic [23:0] sync_pos,
    input  logic [3:0]  miss_limit,
    input  logic        gu_sync,
    input  logic        meas_valid,
    input  logic signed [23:0] meas_err,
    input  logic        ta_set_valid,
    input  logic [23:0] ta_set,
    output logic [23:0] frame_ticks,
    output logic [23:0] dl_ticks,
    output logic [23:0] ul_start,
    output logic [23:0] ul_ticks,
    output logic [1:0]  cls,
    output logic [23:0] ta_ticks,
    output logic [19:0] range_dm,
    output logic        au_fs, au_tx, au_rx, au_ul, au_cfg,
    output logic [23:0] au_cnt,
    output logic        gu_fs, gu_tx, gu_rx, gu_ul, gu_cfg, gu_lost,
    output logic [23:0] gu_cnt,
    output logic signed [24:0] gu_sync_err
);
  logic [23:0] guard;
  logic [15:0] au_fno, gu_fno;
  mac_sched #(.TPU(TPU)) u_sch (.clk(clk), .rst_n(rst_n), .rtt_ticks(rtt_ticks), .update(sched_update), .turn_ticks(turn_ticks),
      .frame_ticks(frame_ticks), .dl_ticks(dl_ticks), .ul_start(ul_start), .ul_ticks(ul_ticks), .guard_ticks(guard), .cls(cls));
  ta_ctrl #(.RES(RES), .TPU(TPU)) u_ta (.clk(clk), .rst_n(rst_n), .meas_valid(meas_valid), .meas_err(meas_err), .ta_set_valid(ta_set_valid),
      .ta_set(ta_set), .ta_max(24'(200 * TPU)), .ta_ticks(ta_ticks), .range_dm(range_dm));
  logic [24:0] au_se;
  logic        au_lost;
  mac_frame_timer u_au (.clk(clk), .rst_n(rst_n), .role(1'b0), .frame_ticks(frame_ticks), .dl_ticks(dl_ticks), .ul_start(ul_start),
      .ul_ticks(ul_ticks), .turn_ticks(turn_ticks), .ta_ticks(24'd0), .sync_pos(24'd0), .miss_limit(4'd0), .sync_valid(1'b0),
      .frame_start(au_fs), .frame_no(au_fno), .cnt(au_cnt), .tx_en(au_tx), .rx_en(au_rx), .ul_win(au_ul), .sync_err(au_se),
      .link_lost(au_lost), .cfg_err(au_cfg));
  mac_frame_timer u_gu (.clk(clk), .rst_n(rst_n), .role(1'b1), .frame_ticks(frame_ticks), .dl_ticks(dl_ticks), .ul_start(ul_start),
      .ul_ticks(ul_ticks), .turn_ticks(turn_ticks), .ta_ticks(ta_ticks), .sync_pos(sync_pos), .miss_limit(miss_limit),
      .sync_valid(gu_sync), .frame_start(gu_fs), .frame_no(gu_fno), .cnt(gu_cnt), .tx_en(gu_tx), .rx_en(gu_rx), .ul_win(gu_ul),
      .sync_err(gu_sync_err), .link_lost(gu_lost), .cfg_err(gu_cfg));
  wire unused_ok = &{1'b0, guard, au_fno, gu_fno, au_se, au_lost};
endmodule
