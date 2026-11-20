// enc_wrap - wrapper around the hard encoder (design/28-encoder-wrapper.md section 1.6).
module enc_wrap #(
    parameter int CODEC = 0,
    parameter int MAX_BYTES = 4096
) (
    input  logic        clk,
    input  logic        rst_n,
    // configuration
    input  logic        frame_src,
    input  logic [7:0]  slices_per_frame,
    input  logic [7:0]  wave_period,
    input  logic [15:0] max_budget,
    input  logic [7:0]  qp_bias_max,
    input  logic        buf_check_en,
    input  logic [15:0] fifo_level,
    // encoder output (Annex-B bytes)
    input  logic        enc_valid,
    output logic        enc_ready,
    input  logic [7:0]  enc_data,
    input  logic        enc_flush,
    input  logic        frame_sync,
    // rate control from module 23
    input  logic        budget_valid,
    input  logic [15:0] budget_in,
    input  logic        qp_valid,
    input  logic [7:0]  qp_bias_in,
    // refresh requests from module 22 and the encoder input frame marker
    input  logic        rf_valid,
    output logic        rf_ready,
    input  logic [15:0] rf_seq,
    input  logic        cmd_start,
    // commands to the encoder
    output logic [15:0] target_bytes,
    output logic        rc_update,
    output logic [7:0]  qp_bias,
    output logic        qp_update,
    output logic [63:0] intra_mask,
    // slice frames to the PHY chain
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [7:0]  m_axis_data,
    output logic        m_axis_last,
    // parameter sets, SEI
    output logic        ps_valid,
    input  logic        ps_ready,
    output logic [7:0]  ps_data,
    output logic        ps_last,
    // monitor
    output logic        mon_done,
    output logic [15:0] mon_size,
    output logic [15:0] mon_ratio_q8,
    output logic        mon_over,
    output logic [15:0] mon_max_ratio_q8,
    output logic [15:0] mon_n_slices,
    output logic [15:0] mon_n_over,
    output logic [15:0] mon_n_zero,
    output logic [15:0] mon_err_buf,
    output logic [15:0] err_overflow,
    output logic [15:0] err_count,
    output logic [15:0] err_rc,
    output logic [15:0] rf_n_req,
    output logic [15:0] rf_n_applied,
    output logic [15:0] rf_n_old
);
  // splitter
  logic        n_valid, n_ready, n_last;
  logic [7:0]  n_data;
  logic [5:0]  nal_type;
  logic        is_slice, is_idr;
  nal_split #(.CODEC(CODEC)) u_split (.clk(clk), .rst_n(rst_n), .flush(enc_flush), .s_valid(enc_valid), .s_ready(enc_ready), .s_data(enc_data),
      .m_valid(n_valid), .m_ready(n_ready), .m_data(n_data), .m_last(n_last), .nal_type(nal_type), .is_slice(is_slice), .is_idr(is_idr),
      .err_overflow(err_overflow));

  // tagger
  logic        t_valid, t_ready, t_last;
  logic [7:0]  t_data;
  logic [15:0] meta_frame;
  logic [7:0]  meta_idx;
  logic [3:0]  meta_flags;
  logic        bs_start;
  logic [15:0] bs_frame;
  logic [63:0] tag_mask;
  slice_tag #(.CODEC(CODEC)) u_tag (.clk(clk), .rst_n(rst_n), .frame_src(frame_src), .frame_sync(frame_sync), .slices_per_frame(slices_per_frame),
      .tag_mask(tag_mask), .s_valid(n_valid), .s_ready(n_ready), .s_data(n_data), .s_last(n_last), .nal_type(nal_type), .is_slice(is_slice),
      .is_idr(is_idr), .m_valid(t_valid), .m_ready(t_ready), .m_data(t_data), .m_last(t_last), .meta_frame(meta_frame), .meta_idx(meta_idx),
      .meta_flags(meta_flags), .ps_valid(ps_valid), .ps_ready(ps_ready), .ps_data(ps_data), .ps_last(ps_last), .bs_start(bs_start),
      .bs_frame(bs_frame), .err_count(err_count));

  // packetiser
  slice_pack #(.MAX_BYTES(MAX_BYTES)) u_pack (.clk(clk), .rst_n(rst_n), .meta_frame(meta_frame), .meta_idx(meta_idx), .meta_flags(meta_flags),
      .s_axis_valid(t_valid), .s_axis_ready(t_ready), .s_axis_data(t_data), .s_axis_last(t_last), .m_axis_valid(m_axis_valid),
      .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data), .m_axis_last(m_axis_last));

  // rate-control hook; the monitor compares every slice with the budget in force when it started
  rc_hook u_rc (.clk(clk), .rst_n(rst_n), .max_budget(max_budget), .budget_valid(budget_valid), .budget_in(budget_in), .qp_valid(qp_valid),
      .qp_bias_in(qp_bias_in), .qp_bias_max(qp_bias_max), .target_bytes(target_bytes), .update(rc_update), .qp_bias(qp_bias), .qp_update(qp_update),
      .err_rc(err_rc));

  // the budget of a frame is the one commanded when the frame went into the encoder: queue it with the frame and use it when the frame leaves
  logic [15:0] bq [8];
  logic [3:0]  bq_n;
  logic [2:0]  bq_rd, bq_wr;
  logic [15:0] budget_tag;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      bq_n <= '0;
      bq_rd <= '0;
      bq_wr <= '0;
      budget_tag <= '0;
    end else begin
      logic [3:0] n_next;
      n_next = bq_n;
      if (bs_start && bq_n != 4'd0) begin
        budget_tag <= bq[bq_rd];
        bq_rd <= bq_rd + 3'd1;
        n_next = n_next - 4'd1;
      end
      if (cmd_start && n_next != 4'd8) begin
        bq[bq_wr] <= target_bytes;
        bq_wr <= bq_wr + 3'd1;
        n_next = n_next + 4'd1;
      end
      bq_n <= n_next;
    end
  end

  wire tap = t_valid & t_ready;
  budget_mon u_mon (.clk(clk), .rst_n(rst_n), .clear(1'b0), .budget(budget_tag), .tap_valid(tap), .tap_last(t_last), .buf_check_en(buf_check_en),
      .fifo_level(fifo_level), .done(mon_done), .size(mon_size), .ratio_q8(mon_ratio_q8), .over(mon_over), .max_ratio_q8(mon_max_ratio_q8),
      .n_slices(mon_n_slices), .n_over(mon_n_over), .n_zero_budget(mon_n_zero), .err_buf(mon_err_buf));

  refresh_map u_ref (.clk(clk), .rst_n(rst_n), .slices_per_frame(slices_per_frame), .wave_period(wave_period), .bs_start(bs_start), .bs_frame(bs_frame),
      .cmd_start(cmd_start), .rf_valid(rf_valid), .rf_ready(rf_ready), .rf_seq(rf_seq), .intra_mask(intra_mask), .tag_mask(tag_mask),
      .n_req(rf_n_req), .n_applied(rf_n_applied), .n_old(rf_n_old));
endmodule
