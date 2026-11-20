// tx_chain - bytes to OFDM samples: framing, LDPC, interleave, map, pilots, IFFT, cyclic prefix (design/16-tx-chain.md).
module tx_chain (
    input  logic        clk,
    input  logic        rst_n,
    // configuration, stable for a whole frame
    input  logic [3:0]  fft_log2,        // 6..9
    input  logic [1:0]  cp_sel,
    input  logic [2:0]  mod,
    input  logic [2:0]  code,
    input  logic [9:0]  shift_mask,
    // frame bytes in
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,
    input  logic        s_axis_last,
    // samples out
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic        m_axis_last,
    output logic        err
);
  // ---------------- derived configuration ----------------
  wire [3:0]  l_cl   = (fft_log2 < 4'd6) ? 4'd6 : (fft_log2 > 4'd9) ? 4'd9 : fft_log2;
  wire [6:0]  zz     = code[2] ? 7'd81 : 7'd27;
  logic [3:0] mb;
  always_comb begin
    case (code[1:0])
      2'd0: mb = 4'd12;
      2'd1: mb = 4'd8;
      2'd2: mb = 4'd6;
      default: mb = 4'd4;
    endcase
  end
  wire [10:0] k_bits = 11'(5'(5'd24 - {1'b0, mb})) * 11'(zz);
  wire [10:0] n_bits = 11'd24 * 11'(zz);
  logic [9:0] nd;
  always_comb begin
    case (l_cl)
      4'd6: nd = 10'd48;
      4'd7: nd = 10'd108;
      4'd8: nd = 10'd234;
      default: nd = 10'd468;
    endcase
  end
  logic [3:0] nb;
  always_comb begin
    case (mod)
      3'd1: nb = 4'd2;
      3'd2: nb = 4'd4;
      3'd3: nb = 4'd6;
      3'd4: nb = 4'd8;
      default: nb = 4'd1;
    endcase
  end
  wire [12:0] ncbps = 13'(nd) * 13'(nb);

  // ---------------- controller state ----------------
  typedef enum logic [1:0] {C_IDLE, C_PRE, C_DATA, C_WAIT} cstate_t;
  cstate_t cstate;
  logic [1:0]  pre_cnt;
  logic [15:0] blk_cnt, iss_cnt, nsym, out_sym;
  logic        fl_seen, in_blocked;

  // ---------------- input: bytes to bits ----------------
  logic        wc_ready, wc_v, wc_l, wc_d_ready;
  logic        wc_dummy;
  logic [0:0]  wc_d;
  wire         in_valid = s_axis_valid & ~in_blocked;
  assign s_axis_ready = wc_ready & ~in_blocked;
  logic wc_err;
  axis_width_conv #(.IN_W(8), .OUT_W(1)) u_wc (
      .clk(clk), .rst_n(rst_n),
      .s_axis_valid(in_valid), .s_axis_ready(wc_ready), .s_axis_data(s_axis_data), .s_axis_last(s_axis_last),
      .m_axis_valid(wc_v), .m_axis_ready(wc_d_ready), .m_axis_data(wc_d), .m_axis_last(wc_l), .err_frame(wc_err));

  logic        mp_v, mp_r, mp_l, mp_fl;
  logic [31:0] mp_d;
  msg_bits_pack u_pack (
      .clk(clk), .rst_n(rst_n), .k_bits(k_bits),
      .s_valid(wc_v), .s_ready(wc_d_ready), .s_data(wc_d[0]), .s_last(wc_l),
      .m_valid(mp_v), .m_ready(mp_r), .m_data(mp_d), .m_last(mp_l), .m_frame_last(mp_fl));

  // ---------------- LDPC encoder with the frame-final flag queue ----------------
  logic        enc_s_ready, enc_m_v, enc_m_r, enc_m_l, enc_err;
  logic [31:0] enc_m_d;
  assign mp_r = enc_s_ready;
  ldpc_enc u_enc (
      .clk(clk), .rst_n(rst_n), .code(code),
      .s_axis_valid(mp_v), .s_axis_ready(enc_s_ready), .s_axis_data(mp_d), .s_axis_last(mp_l),
      .m_axis_valid(enc_m_v), .m_axis_ready(enc_m_r), .m_axis_data(enc_m_d), .m_axis_last(enc_m_l), .err_len(enc_err));

  logic fq_ready, fq_v, fq_d, fq_l;
  logic [2:0] fq_level;
  wire  push_flag = mp_v & enc_s_ready & mp_l;
  wire  take_last = enc_m_v & enc_m_r & enc_m_l;
  axis_fifo #(.W(1), .DEPTH(4)) u_fq (
      .clk(clk), .rst_n(rst_n),
      .s_axis_valid(push_flag), .s_axis_ready(fq_ready), .s_axis_data(mp_fl), .s_axis_last(1'b0),
      .m_axis_valid(fq_v), .m_axis_ready(take_last), .m_axis_data(fq_d), .m_axis_last(fq_l), .level(fq_level));

  logic cb_v, cb_r, cb_l, cb_fl, cb_d, cw_s_ready;
  assign enc_m_r = cw_s_ready;
  cw_to_bits u_cw (
      .clk(clk), .rst_n(rst_n), .n_bits(n_bits),
      .s_valid(enc_m_v), .s_ready(cw_s_ready), .s_data(enc_m_d), .s_last(enc_m_l), .s_fl(fq_d),
      .m_valid(cb_v), .m_ready(cb_r), .m_data(cb_d), .m_last(cb_l), .m_fl(cb_fl));

  // ---------------- symbol blocks, interleave, pack, map ----------------
  logic sb_v, sb_r, sb_d, sb_l, blk_pulse, blk_fl;
  sym_blocker u_blk (
      .clk(clk), .rst_n(rst_n), .ncbps(ncbps),
      .s_valid(cb_v), .s_ready(cb_r), .s_data(cb_d), .s_last(cb_l), .s_fl(cb_fl),
      .m_valid(sb_v), .m_ready(sb_r), .m_data(sb_d), .m_last(sb_l), .blk_pulse(blk_pulse), .blk_fl(blk_fl));

  logic il_v, il_r, il_l, il_err;
  logic [0:0] il_d;
  logic [12:0] il_n;
  block_interleaver #(.W(1), .MAX_N(4096), .DEINT(1'b0)) u_il (
      .clk(clk), .rst_n(rst_n), .n(ncbps),
      .s_axis_valid(sb_v), .s_axis_ready(sb_r), .s_axis_data(sb_d), .s_axis_last(sb_l),
      .m_axis_valid(il_v), .m_axis_ready(il_r), .m_axis_data(il_d), .m_axis_last(il_l), .m_n(il_n), .err_len(il_err));

  logic bp_v, bp_r, bp_l;
  logic [7:0] bp_d;
  bit_packer u_bp (
      .clk(clk), .rst_n(rst_n), .nb(nb),
      .s_valid(il_v), .s_ready(il_r), .s_data(il_d[0]), .s_last(il_l),
      .m_valid(bp_v), .m_ready(bp_r), .m_data(bp_d), .m_last(bp_l));

  logic mm_v, mm_r, mm_l;
  logic [31:0] mm_d;
  mapper u_map (
      .clk(clk), .rst_n(rst_n), .mod(mod),
      .s_axis_valid(bp_v), .s_axis_ready(bp_r), .s_axis_data(bp_d), .s_axis_last(bp_l),
      .m_axis_valid(mm_v), .m_axis_ready(mm_r), .m_axis_data(mm_d), .m_axis_last(mm_l));

  // ---------------- tone plan and assembly ----------------
  logic        cmd_valid, cmd_ready;
  logic [1:0]  cmd_kind;
  logic        cmd_fs;
  logic        pg_v, pg_r, pg_l;
  logic [33:0] pg_d;
  preamble_gen u_pg (
      .clk(clk), .rst_n(rst_n),
      .cmd_valid(cmd_valid), .cmd_ready(cmd_ready), .cmd_kind(cmd_kind), .cmd_log2(l_cl), .cmd_frame_start(cmd_fs),
      .m_axis_valid(pg_v), .m_axis_ready(pg_r), .m_axis_data(pg_d), .m_axis_last(pg_l));

  logic as_v, as_r, as_l;
  logic [31:0] as_d;
  tx_assembler u_as (
      .pg_valid(pg_v), .pg_ready(pg_r), .pg_data(pg_d), .pg_last(pg_l),
      .mp_valid(mm_v), .mp_ready(mm_r), .mp_data(mm_d),
      .m_valid(as_v), .m_ready(as_r), .m_data(as_d), .m_last(as_l));

  // ---------------- IFFT and cyclic prefix ----------------
  logic ff_v, ff_r, ff_l, fft_err;
  logic [31:0] ff_d;
  logic [15:0] ovf;
  fft_core #(.MAX_LOG2(9)) u_fft (
      .clk(clk), .rst_n(rst_n), .fft_log2(l_cl), .inverse(1'b1), .shift_mask(shift_mask),
      .s_axis_valid(as_v), .s_axis_ready(as_r), .s_axis_data(as_d), .s_axis_last(as_l),
      .m_axis_valid(ff_v), .m_axis_ready(ff_r), .m_axis_data(ff_d), .m_axis_last(ff_l), .ovf_cnt(ovf), .err_len(fft_err));

  logic cp_v, cp_l, cp_err;
  logic [31:0] cp_d;
  cp_insert #(.W(32), .MAX_LOG2(9)) u_cp (
      .clk(clk), .rst_n(rst_n), .fft_log2(l_cl), .cp_sel(cp_sel),
      .s_axis_valid(ff_v), .s_axis_ready(ff_r), .s_axis_data(ff_d), .s_axis_last(ff_l),
      .m_axis_valid(cp_v), .m_axis_ready(m_axis_ready), .m_axis_data(cp_d), .m_axis_last(cp_l), .err_len(cp_err));

  // ---------------- controller ----------------
  wire cmd_xfer = cmd_valid & cmd_ready;
  wire out_xfer = cp_v & m_axis_ready;
  wire final_sym = fl_seen && (out_sym == nsym + 16'd2);
  wire frame_done = out_xfer & cp_l & final_sym;

  assign m_axis_valid = cp_v;
  assign m_axis_data  = cp_d;
  assign m_axis_last  = cp_l & final_sym;

  always_comb begin
    cmd_valid = 1'b0;
    cmd_kind  = 2'd2;
    cmd_fs    = 1'b0;
    if (cstate == C_PRE) begin
      cmd_valid = 1'b1;
      cmd_kind  = (pre_cnt == 2'd0) ? 2'd0 : 2'd1;
    end else if (cstate == C_DATA && iss_cnt < blk_cnt) begin
      cmd_valid = 1'b1;
      cmd_kind  = 2'd2;
      cmd_fs    = (iss_cnt == 16'd0);
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      cstate     <= C_IDLE;
      pre_cnt    <= '0;
      blk_cnt    <= '0;
      iss_cnt    <= '0;
      nsym       <= '0;
      out_sym    <= '0;
      fl_seen    <= 1'b0;
      in_blocked <= 1'b0;
      err        <= 1'b0;
    end else begin
      err <= wc_err | enc_err | il_err | fft_err | cp_err | (ncbps > 13'd4096);
      if (blk_pulse) begin
        blk_cnt <= blk_cnt + 16'd1;
        if (blk_fl) begin
          fl_seen <= 1'b1;
          nsym    <= blk_cnt + 16'd1;
        end
      end
      if (in_valid && wc_ready && s_axis_last) in_blocked <= 1'b1;
      if (out_xfer && cp_l) out_sym <= out_sym + 16'd1;
      case (cstate)
        C_IDLE: if (s_axis_valid && !in_blocked) cstate <= C_PRE;
        C_PRE: if (cmd_xfer) begin
          if (pre_cnt == 2'd2) begin
            pre_cnt <= '0;
            cstate  <= C_DATA;
          end else pre_cnt <= pre_cnt + 2'd1;
        end
        C_DATA: if (cmd_xfer) begin
          iss_cnt <= iss_cnt + 16'd1;
          if ((fl_seen || (blk_pulse && blk_fl)) && (iss_cnt + 16'd1 == (fl_seen ? nsym : blk_cnt + 16'd1))) cstate <= C_WAIT;
        end
        default: ;
      endcase
      if (frame_done) begin
        cstate     <= C_IDLE;
        blk_cnt    <= blk_pulse ? 16'd1 : 16'd0;
        iss_cnt    <= '0;
        nsym       <= '0;
        out_sym    <= '0;
        fl_seen    <= 1'b0;
        in_blocked <= 1'b0;
      end
    end
  end

  wire unused_ok = &{1'b0, wc_dummy, fq_ready, fq_v, fq_l, fq_level, il_n, ovf, mm_l};
  assign wc_dummy = 1'b0;
endmodule
