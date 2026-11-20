// retx_ctrl - selective retransmission and refresh decision from the acknowledgement bitmap
// (design/22-tdd-mac.md section 2.5).
module retx_ctrl (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [31:0] now,
    input  logic [31:0] tx_ticks,            // estimated airtime of a slice
    input  logic [31:0] owd_ticks,           // one-way delay
    input  logic [3:0]  max_retx,
    input  logic [3:0]  holdoff,
    input  logic [31:0] tmo_ticks,           // an unacknowledged slice older than this counts as lost (0: off); covers losses at the end of a burst
    // slices sent
    input  logic        sent_valid,
    input  logic [15:0] sent_seq,
    input  logic [31:0] sent_deadline,
    // feedback
    input  logic        fb_valid,
    output logic        fb_ready,
    input  logic [15:0] fb_hi,
    input  logic [63:0] fb_bits,
    // retransmission queue
    output logic        rtx_valid,
    input  logic        rtx_ready,
    output logic [15:0] rtx_seq,
    // refresh queue
    output logic        rf_valid,
    input  logic        rf_ready,
    output logic [15:0] rf_seq,
    output logic [15:0] drop_cnt,
    output logic [15:0] stale_cnt,
    output logic [15:0] ovf_cnt,
    output logic        busy
);
  logic [15:0] t_seq  [64];
  logic [31:0] t_dl   [64];
  logic [31:0] t_ts   [64];
  logic [3:0]  t_cnt  [64];
  logic [63:0] t_val;

  // queues
  logic [15:0] rq [16];
  logic [15:0] fq [16];
  logic [4:0]  rq_n, fq_n;
  logic [3:0]  rq_rd, fq_rd;
  assign rtx_valid = (rq_n != 5'd0);
  assign rtx_seq   = rq[rq_rd];
  assign rf_valid  = (fq_n != 5'd0);
  assign rf_seq    = fq[fq_rd];

  logic [15:0] hi_l;
  logic [63:0] bits_l;
  logic [31:0] now_l;
  logic [6:0]  pos;
  logic sweeping;
  assign busy     = sweeping;
  assign fb_ready = !sweeping;

  wire [15:0] seq_p = hi_l - 16'd63 + {9'd0, pos[5:0]};
  wire [5:0]  idx   = seq_p[5:0];
  wire        here  = t_val[idx] && (t_seq[idx] == seq_p);
  wire signed [15:0] older = $signed(t_seq[idx] - seq_p);          // < 0: entry older than this window position
  wire signed [15:0] age   = $signed(seq_p - (hi_l - {12'd0, holdoff}));   // <= 0: old enough to be called lost
  wire        timed_out = (tmo_ticks != 32'd0) && ((now_l - t_ts[idx]) >= tmo_ticks) && t_val[idx];
  wire signed [31:0] slack = $signed(t_dl[idx] - now_l);
  wire        can_retx = (t_cnt[idx] < max_retx) && (slack >= $signed(tx_ticks + owd_ticks)) && (rq_n < 5'd16);

  logic pop_r, pop_f;
  assign pop_r = rtx_valid && rtx_ready;
  assign pop_f = rf_valid && rf_ready;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      t_val     <= '0;
      rq_n      <= '0;
      fq_n      <= '0;
      rq_rd     <= '0;
      fq_rd     <= '0;
      sweeping  <= 1'b0;
      pos       <= '0;
      drop_cnt  <= '0;
      stale_cnt <= '0;
      ovf_cnt   <= '0;
    end else begin
      logic [4:0] rn, fn;
      logic [3:0] rw, fw;
      logic [15:0] sc, dc, oc;
      rn = rq_n;
      sc = stale_cnt;
      dc = drop_cnt;
      oc = ovf_cnt;
      fn = fq_n;
      rw = rq_rd + rq_n[3:0];
      fw = fq_rd + fq_n[3:0];
      if (pop_r) begin rq_rd <= rq_rd + 4'd1; rn = rn - 5'd1; end
      if (pop_f) begin fq_rd <= fq_rd + 4'd1; fn = fn - 5'd1; end

      if (fb_valid && !sweeping) begin
        hi_l     <= fb_hi;
        bits_l   <= fb_bits;
        now_l    <= now;
        sweeping <= 1'b1;
        pos      <= '0;
      end else if (sweeping) begin
        if (t_val[idx] && (here || older > 0) && !(here && bits_l[pos[5:0]])) begin
          // an unacknowledged entry: lost if the bitmap says so for an old enough slice, or if it timed out
          if ((here && age <= 0) || timed_out) begin
            if (can_retx) begin
              rq[rw] <= t_seq[idx];
              rn = rn + 5'd1;
              t_cnt[idx] <= t_cnt[idx] + 4'd1;
              t_ts[idx] <= now_l;
            end else begin
              t_val[idx] <= 1'b0;
              dc = dc + 16'd1;
              if (fn < 5'd16) begin
                fq[fw] <= t_seq[idx];
                fn = fn + 5'd1;
              end else oc = oc + 16'd1;
            end
          end
        end else if (here) begin
          t_val[idx] <= 1'b0;                   // acknowledged
        end else if (t_val[idx] && older < 0) begin
          t_val[idx] <= 1'b0;
          sc = sc + 16'd1;
        end
        if (pos == 7'd63) begin
          sweeping <= 1'b0;
          pos      <= '0;
        end else pos <= pos + 7'd1;
      end
      // a slice sent in this clock has priority over the sweep's update of the same entry
      if (sent_valid) begin
        if (t_val[sent_seq[5:0]] && t_seq[sent_seq[5:0]] == sent_seq) begin
          // retransmission of a known slice: keep its deadline and count, restart its timer
          t_ts[sent_seq[5:0]] <= now;
        end else begin
          if (t_val[sent_seq[5:0]]) sc = sc + 16'd1;
          t_val[sent_seq[5:0]] <= 1'b1;
          t_seq[sent_seq[5:0]] <= sent_seq;
          t_dl [sent_seq[5:0]] <= sent_deadline;
          t_cnt[sent_seq[5:0]] <= '0;
          t_ts [sent_seq[5:0]] <= now;
        end
      end

      stale_cnt <= sc;
      drop_cnt  <= dc;
      ovf_cnt   <= oc;
      rq_n <= rn;
      fq_n <= fn;
    end
  end
endmodule
