// refresh_map - lost slice sequence numbers to intra-refresh commands (design/28-encoder-wrapper.md section 1.4).
module refresh_map (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  slices_per_frame,
    input  logic [7:0]  wave_period,            // 0: no rolling wave; else slice (frame mod period) is forced intra
    // bitstream side: a frame boundary of the encoder output
    input  logic        bs_start,
    input  logic [15:0] bs_frame,               // frame number before the boundary
    // encoder input side: a frame is about to be coded
    input  logic        cmd_start,
    // lost slices from the MAC
    input  logic        rf_valid,
    output logic        rf_ready,
    input  logic [15:0] rf_seq,
    // outputs
    output logic [63:0] intra_mask,             // to the encoder, latched at cmd_start
    output logic [63:0] tag_mask,               // for the frame now leaving the encoder: the oldest mask not yet used (popped at bs_start)
    output logic [15:0] n_req,
    output logic [15:0] n_applied,
    output logic [15:0] n_old
);
  logic [15:0] ring_first [16];
  logic [15:0] ring_v;
  logic [3:0]  rp;
  logic [63:0] pending;
  logic [63:0] q [8];
  logic [3:0]  q_n;
  logic [2:0]  q_rd, q_wr;
  logic [15:0] cmd_frames;

  assign rf_ready = 1'b1;
  assign tag_mask = (q_n != 4'd0) ? q[q_rd] : 64'd0;

  logic        hit;
  logic [7:0]  hit_idx;
  always_comb begin
    hit = 1'b0;
    hit_idx = '0;
    for (int k = 0; k < 16; k++) begin
      logic [15:0] d;
      d = rf_seq - ring_first[k];
      if (ring_v[k] && d < {8'd0, slices_per_frame} && !hit) begin
        hit = 1'b1;
        hit_idx = d[7:0];
      end
    end
  end

  wire [15:0] wphase = (wave_period != 8'd0) ? (cmd_frames % {8'd0, wave_period}) : 16'd0;
  wire        wave_on = (wave_period != 8'd0) && (wphase < {8'd0, slices_per_frame}) && (wphase < 16'd64);
  wire [63:0] wave_bit = wave_on ? (64'd1 << wphase[5:0]) : 64'd0;
  wire [63:0] req_bit = (rf_valid && hit && hit_idx < 8'd64) ? (64'd1 << hit_idx[5:0]) : 64'd0;
  wire [63:0] m_next = pending | wave_bit | req_bit;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      ring_v <= '0;
      rp <= '0;
      pending <= '0;
      intra_mask <= '0;
      n_req <= '0;
      n_applied <= '0;
      n_old <= '0;
      cmd_frames <= '0;
      q_n <= '0;
      q_rd <= '0;
      q_wr <= '0;
      /* verilator lint_off BLKSEQ */
      for (int k = 0; k < 16; k++) ring_first[k] = '0;
      for (int k = 0; k < 8; k++) q[k] = '0;
      /* verilator lint_on BLKSEQ */
    end else begin
      logic [3:0] n_next;
      n_next = q_n;
      if (bs_start) begin
        ring_first[rp] <= (bs_frame + 16'd1) * {8'd0, slices_per_frame};
        ring_v[rp] <= 1'b1;
        rp <= rp + 4'd1;
        if (q_n != 4'd0) begin
          q_rd <= q_rd + 3'd1;
          n_next = n_next - 4'd1;
        end
      end
      if (rf_valid) begin
        n_req <= n_req + 16'd1;
        if (!hit) n_old <= n_old + 16'd1;
        else if ((pending & req_bit) == 64'd0 && req_bit != 64'd0) n_applied <= n_applied + 16'd1;
      end
      if (cmd_start) begin
        intra_mask <= m_next;
        if (n_next != 4'd8) begin
          q[q_wr] <= m_next;
          q_wr <= q_wr + 3'd1;
          n_next = n_next + 4'd1;
        end
        pending <= '0;
        cmd_frames <= cmd_frames + 16'd1;
      end else if (rf_valid && hit) begin
        pending <= pending | req_bit;
      end
      q_n <= n_next;
    end
  end
endmodule
