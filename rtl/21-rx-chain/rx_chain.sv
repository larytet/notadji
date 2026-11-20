// rx_chain - samples to bytes: synchroniser, windows, FFT, equaliser, demapper, de-interleaver, LDPC decoder (design/21-rx-chain.md).
module rx_chain (
    input  logic        clk,
    input  logic        rst_n,
    // configuration, stable for a frame
    input  logic [3:0]  fft_log2,
    input  logic [1:0]  cp_sel,
    input  logic [2:0]  mod,
    input  logic [2:0]  code,
    input  logic [15:0] nsym,
    input  logic [7:0]  ncw,
    input  logic [15:0] nbytes,
    input  logic [3:0]  backoff,
    input  logic [1:0]  thr_sel,
    input  logic [31:0] min_power,
    // samples in
    input  logic        s_valid,
    input  logic [31:0] s_data,
    // bytes out
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [7:0]  m_axis_data,
    output logic        m_axis_last,
    output logic        frame_ok,
    output logic [5:0]  iters_max,
    output logic        det,
    output logic signed [23:0] cfo_inc,
    output logic [12:0] fifo_max,
    output logic        err
);
  // ---------------- derived configuration ----------------
  wire [3:0]  l_cl = (fft_log2 < 4'd6) ? 4'd6 : (fft_log2 > 4'd9) ? 4'd9 : fft_log2;
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
  logic [3:0] llr_sh;
  always_comb begin
    case (mod)
      3'd1: begin nb = 4'd2; llr_sh = 4'd13; end
      3'd2: begin nb = 4'd4; llr_sh = 4'd12; end
      3'd3: begin nb = 4'd6; llr_sh = 4'd11; end
      3'd4: begin nb = 4'd8; llr_sh = 4'd10; end
      default: begin nb = 4'd1; llr_sh = 4'd13; end
    endcase
  end
  wire [12:0] ncbps = 13'(nd) * 13'(nb);
  wire [6:0]  zz    = code[2] ? 7'd81 : 7'd27;
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
  wire [23:0] frame_llr = 24'(nsym) * 24'(ncbps);
  wire [15:0] total_llr = 16'(ncw) * 16'(n_bits);

  // ---------------- synchroniser and windows ----------------
  logic        sy_v, sy_fall, sy_locked, sy_mok, sy_up, sy_dn;
  logic [31:0] sy_d;
  logic [15:0] sy_ang;
  logic [7:0]  k_back;
  logic        frame_done, rearm;
  sync_core #(.MAX_LOG2(9)) u_sync (
      .clk(clk), .rst_n(rst_n), .fft_log2(l_cl), .thr_sel(thr_sel), .min_power(min_power), .agc_lo(32'd0), .agc_hi(32'hFFFFFFFF),
      .rearm(rearm), .s_valid(s_valid), .s_data(s_data), .m_valid(sy_v), .m_data(sy_d), .det(det), .cfo_inc(cfo_inc),
      .cfo_angle(sy_ang), .fall(sy_fall), .k_back(k_back), .metric_ok(sy_mok), .agc_up(sy_up), .agc_down(sy_dn), .locked(sy_locked));

  logic        fr_v, fr_l, fr_active, err_skip;
  logic [31:0] fr_d;
  rx_framer u_frm (
      .clk(clk), .rst_n(rst_n), .fft_log2(l_cl), .cp_sel(cp_sel), .backoff(backoff), .k_back(k_back), .nwin(nsym + 16'd2),
      .fall(sy_fall), .rearm(rearm), .s_valid(sy_v), .s_data(sy_d), .m_valid(fr_v), .m_data(fr_d), .m_last(fr_l),
      .err_skip(err_skip), .active(fr_active));

  // ---------------- FFT ----------------
  logic        ff_in_ready, ff_v, ff_l, ff_err;
  logic [31:0] ff_d;
  logic [15:0] ovf;
  logic        eq_ready;
  fft_core #(.MAX_LOG2(9)) u_fft (
      .clk(clk), .rst_n(rst_n), .fft_log2(l_cl), .inverse(1'b0), .shift_mask(10'h007),
      .s_axis_valid(fr_v), .s_axis_ready(ff_in_ready), .s_axis_data(fr_d), .s_axis_last(fr_l),
      .m_axis_valid(ff_v), .m_axis_ready(eq_ready), .m_axis_data(ff_d), .m_axis_last(ff_l), .ovf_cnt(ovf), .err_len(ff_err));
  wire drop_err = fr_v & ~ff_in_ready;

  // ---------------- equaliser ----------------
  logic [15:0] eq_sym;
  logic [1:0]  eq_kind;
  always_comb begin
    case (eq_sym)
      16'd0: eq_kind = 2'd0;
      16'd1: eq_kind = 2'd1;
      16'd2: eq_kind = 2'd2;
      default: eq_kind = 2'd3;
    endcase
  end
  logic        dm_in_ready;
  logic        eq_v, eq_l, eq_err, eq_in_xfer;
  logic [31:0] eq_d;
  logic [7:0]  eq_csi;
  equalizer #(.MAX_LOG2(9)) u_eq (
      .clk(clk), .rst_n(rst_n), .fft_log2(l_cl), .kind(eq_kind),
      .s_axis_valid(ff_v), .s_axis_ready(eq_ready), .s_axis_data(ff_d), .s_axis_last(ff_l),
      .m_axis_valid(eq_v), .m_axis_ready(dm_in_ready), .m_axis_data(eq_d), .m_csi(eq_csi), .m_axis_last(eq_l), .err_len(eq_err));
  assign eq_in_xfer = ff_v & eq_ready & ff_l;

  // ---------------- demapper, serializer, de-interleaver ----------------
  logic        dm_v, dm_l, dm_r;
  logic [63:0] dm_d;
  logic [3:0]  dm_nb;
  demapper u_dm (
      .clk(clk), .rst_n(rst_n), .mod(mod), .llr_shift(llr_sh),
      .s_axis_valid(eq_v), .s_axis_ready(dm_in_ready), .s_axis_data(eq_d), .s_csi(eq_csi), .s_axis_last(eq_l),
      .m_axis_valid(dm_v), .m_axis_ready(dm_r), .m_axis_data(dm_d), .m_nbits(dm_nb), .m_axis_last(dm_l));

  logic        sr_v, sr_r, sr_l;
  logic [7:0]  sr_d;
  llr_serializer u_ser (
      .clk(clk), .rst_n(rst_n), .s_axis_valid(dm_v), .s_axis_ready(dm_r), .s_axis_data(dm_d), .s_nbits(dm_nb), .s_axis_last(dm_l),
      .m_axis_valid(sr_v), .m_axis_ready(sr_r), .m_axis_data(sr_d), .m_axis_last(sr_l));

  logic        il_v, il_r, il_l, il_err;
  logic [7:0]  il_d;
  logic [12:0] il_n;
  block_interleaver #(.W(8), .MAX_N(4096), .DEINT(1'b1)) u_il (
      .clk(clk), .rst_n(rst_n), .n(ncbps),
      .s_axis_valid(sr_v), .s_axis_ready(sr_r), .s_axis_data(sr_d), .s_axis_last(sr_l),
      .m_axis_valid(il_v), .m_axis_ready(il_r), .m_axis_data(il_d), .m_axis_last(il_l), .m_n(il_n), .err_len(il_err));

  // ---------------- trim, FIFO, decoder ----------------
  logic        tr_v, tr_r, tr_l;
  logic [7:0]  tr_d;
  llr_trim u_trim (
      .clk(clk), .rst_n(rst_n), .total(total_llr), .n_cw(n_bits), .frame_llr(frame_llr), .clr(1'b0),
      .s_valid(il_v), .s_ready(il_r), .s_data(il_d), .m_valid(tr_v), .m_ready(tr_r), .m_data(tr_d), .m_last(tr_l));

  logic        ff2_v, ff2_r, ff2_l;
  logic [7:0]  ff2_d;
  logic [12:0] ff2_level;
  axis_fifo #(.W(8), .DEPTH(4096)) u_fifo (
      .clk(clk), .rst_n(rst_n),
      .s_axis_valid(tr_v), .s_axis_ready(tr_r), .s_axis_data(tr_d), .s_axis_last(tr_l),
      .m_axis_valid(ff2_v), .m_axis_ready(ff2_r), .m_axis_data(ff2_d), .m_axis_last(ff2_l), .level(ff2_level));

  logic        dc_v, dc_r, dc_l, dc_ok, dc_err;
  logic [31:0] dc_d;
  logic [5:0]  dc_it;
  ldpc_dec u_dec (
      .clk(clk), .rst_n(rst_n), .code(code), .max_iter(6'd10),
      .s_axis_valid(ff2_v), .s_axis_ready(ff2_r), .s_axis_data($signed(ff2_d)), .s_axis_last(ff2_l),
      .m_axis_valid(dc_v), .m_axis_ready(dc_r), .m_axis_data(dc_d), .m_axis_last(dc_l), .m_ok(dc_ok), .m_iters(dc_it), .err_len(dc_err));

  // ---------------- message bits to bytes ----------------
  logic        cb_v, cb_r, cb_l, cb_fl, cb_d;
  cw_to_bits u_cw (
      .clk(clk), .rst_n(rst_n), .n_bits(k_bits),
      .s_valid(dc_v), .s_ready(dc_r), .s_data(dc_d), .s_last(dc_l), .s_fl(1'b0),
      .m_valid(cb_v), .m_ready(cb_r), .m_data(cb_d), .m_last(cb_l), .m_fl(cb_fl));

  msg_to_bytes u_m2b (
      .clk(clk), .rst_n(rst_n), .nbytes(nbytes), .ncw(ncw),
      .s_valid(cb_v), .s_ready(cb_r), .s_data(cb_d), .s_last(cb_l),
      .m_valid(m_axis_valid), .m_ready(m_axis_ready), .m_data(m_axis_data), .m_last(m_axis_last), .frame_done(frame_done));

  // frame status: AND of the codeword status values, largest iteration count
  logic first_word, ok_acc;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      first_word <= 1'b1;
      ok_acc     <= 1'b1;
      frame_ok   <= 1'b0;
      iters_max  <= '0;
      eq_sym     <= '0;
      fifo_max   <= '0;
      err        <= 1'b0;
    end else begin
      err <= err_skip | drop_err | ff_err | eq_err | il_err | dc_err;
      if (ff2_level > fifo_max) fifo_max <= ff2_level;
      if (eq_in_xfer) eq_sym <= eq_sym + 16'd1;
      if (dc_v && dc_r && first_word) begin
        ok_acc <= ok_acc & dc_ok;
        if (dc_it > iters_max) iters_max <= dc_it;
        first_word <= 1'b0;
      end
      if (dc_v && dc_r && dc_l) first_word <= 1'b1;
      if (frame_done) begin
        frame_ok   <= ok_acc;
        ok_acc     <= 1'b1;
        iters_max  <= '0;
        eq_sym     <= '0;
        fifo_max   <= '0;
        first_word <= 1'b1;
      end
    end
  end
  assign rearm = frame_done;

  wire unused_ok = &{1'b0, sy_v, sy_locked, sy_mok, sy_up, sy_dn, sy_ang, fr_active, ovf, il_n, il_l, cb_fl};
endmodule
