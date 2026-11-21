// Module 31: M-point DFT / IDFT for M = 48, 96, 192, 384 (three power-of-two FFTs of module 12 and a radix-3 combine).
// Definition: design/31-dft-s-ofdm.md section 2 (bit-exact model: tests/31-dft-s-ofdm/dfts_model.py).
module dft_mixed (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [1:0]  m_sel,          // 0..3: M = 48, 96, 192, 384 (sampled with the first input sample)
    input  logic        inverse,
    input  logic [8:0]  in_rot,         // input sample i goes to x[(i + in_rot) mod M]
    input  logic [8:0]  out_rot,        // output sample n is X[(n + out_rot) mod M]
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [31:0] s_axis_data,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic        m_axis_last,
    output logic [15:0] ovf_cnt,
    output logic        err_len
);
  localparam int MMAX = 384;
  localparam int LMAX = 128;

  function automatic [8:0] f_m(input [1:0] s);
    f_m = 9'd48 << s;
  endfunction
  function automatic [7:0] f_l(input [1:0] s);
    f_l = 8'd16 << s;
  endfunction
  function automatic [9:0] f_mask(input [1:0] s);
    case (s)
      2'd0: f_mask = 10'h003;
      2'd1: f_mask = 10'h007;
      2'd2: f_mask = 10'h007;
      default: f_mask = 10'h00F;
    endcase
  endfunction
  function automatic signed [15:0] f_cm(input s0);
    f_cm = s0 ? 16'sd13377 : 16'sd9459;
  endfunction
  function automatic signed [15:0] sat16(input signed [39:0] v);
    if (v > 40'sd32767) sat16 = 16'sd32767;
    else if (v < -40'sd32768) sat16 = -16'sd32768;
    else sat16 = v[15:0];
  endfunction
  function automatic logic is_sat(input signed [39:0] v);
    is_sat = (v > 40'sd32767) || (v < -40'sd32768);
  endfunction

  // ---------------- storage ----------------
  logic [31:0] xmem [MMAX];
  logic [31:0] y0 [LMAX];
  logic [31:0] y1 [LMAX];
  logic [31:0] y2 [LMAX];
  logic [31:0] o0 [LMAX];
  logic [31:0] o1 [LMAX];
  logic [31:0] o2 [LMAX];

  // ---------------- stage configuration ----------------
  logic [1:0] ci_sel_q;
  logic       ci_inv_q;
  logic [8:0] ci_irot_q, ci_orot_q;
  logic [1:0] cf_sel;     logic cf_inv;   logic [8:0] cf_orot;     // feed / collect stage
  logic [1:0] cc_sel;     logic cc_inv;   logic [8:0] cc_orot;     // combine stage
  logic [1:0] co_sel;     logic [8:0] co_orot;                      // output stage

  // ---------------- input ----------------
  logic [8:0] icnt;
  logic       x_full;
  wire        i_first = (icnt == 9'd0);
  wire [1:0]  i_sel   = i_first ? m_sel : ci_sel_q;
  wire [8:0]  i_irot  = i_first ? in_rot : ci_irot_q;
  wire [8:0]  i_m     = f_m(i_sel);
  wire [9:0]  i_idx0  = {1'b0, icnt} + {1'b0, i_irot};
  wire [8:0]  i_idx   = (i_idx0 >= {1'b0, i_m}) ? 9'(i_idx0 - {1'b0, i_m}) : i_idx0[8:0];
  assign s_axis_ready = ~x_full;
  wire in_xfer = s_axis_valid & s_axis_ready;
  wire i_lastbeat = (icnt == i_m - 9'd1);

  // ---------------- FFT instance ----------------
  logic        f_active;
  logic [1:0]  fr;
  logic [7:0]  fm;
  logic        ff_ready, ff_v, ff_l;
  logic [31:0] ff_d;
  logic [15:0] fft_ovf;
  logic        fft_err;
  wire  [7:0]  f_lc = f_l(cf_sel);
  wire  [9:0]  fa10 = {2'b00, fm} + {1'b0, fm, 1'b0} + {8'd0, fr};      // 3 m + r
  wire  [8:0]  fa   = fa10[8:0];
  wire         feed_v = f_active;
  wire         feed_x = feed_v & ff_ready;
  fft_core #(.MAX_LOG2(7), .MIN_LOG2(4)) u_fft (
      .clk(clk), .rst_n(rst_n), .fft_log2(4'd4 + {2'b00, cf_sel}), .inverse(cf_inv), .shift_mask(f_mask(cf_sel)),
      .s_axis_valid(feed_v), .s_axis_ready(ff_ready), .s_axis_data(xmem[fa]), .s_axis_last(fm == f_lc - 8'd1),
      .m_axis_valid(ff_v), .m_axis_ready(1'b1), .m_axis_data(ff_d), .m_axis_last(ff_l), .ovf_cnt(fft_ovf), .err_len(fft_err));

  // collector
  logic        c_active, y_full, comb_act;
  logic [1:0]  cr;
  logic [7:0]  ck;
  // combine
  logic [7:0]  kk;
  logic        o_full, out_act;
  logic [8:0]  oc;
  logic [15:0] own_ovf;

  // ---------------- combine datapath (combinational, one k per clock) ----------------
  wire  [7:0]  cl_c = f_l(cc_sel);
  wire  [8:0]  k2 = {kk, 1'b0};
  logic signed [15:0] w1c, w1s, w2c, w2s;
  dfts_twiddle_rom u_t1 (.m_sel(cc_sel), .n({1'b0, kk}), .cos_q(w1c), .sin_q(w1s));
  dfts_twiddle_rom u_t2 (.m_sel(cc_sel), .n(k2), .cos_q(w2c), .sin_q(w2s));
  logic [31:0] ya, yb, yc;
  assign ya = y0[kk[6:0]];
  assign yb = y1[kk[6:0]];
  assign yc = y2[kk[6:0]];
  logic signed [15:0] ar, ai;
  logic signed [39:0] br, bi, cr_, ci_, tr, ti, dr, di, ur, ui, vr, vi, x0r, x0i, x1r, x1i, x2r, x2i;
  logic signed [39:0] s1, s2, s3, s4;
  logic signed [15:0] wib, wic;
  logic signed [39:0] cmv;
  always_comb begin
    ar = ya[15:0];
    ai = ya[31:16];
    wib = cc_inv ? w1s : -w1s;
    wic = cc_inv ? w2s : -w2s;
    br  = ((40'(signed'(yb[15:0])) * 40'(w1c) - 40'(signed'(yb[31:16])) * 40'(wib)) + 40'sd16384) >>> 15;
    bi  = ((40'(signed'(yb[15:0])) * 40'(wib) + 40'(signed'(yb[31:16])) * 40'(w1c)) + 40'sd16384) >>> 15;
    cr_ = ((40'(signed'(yc[15:0])) * 40'(w2c) - 40'(signed'(yc[31:16])) * 40'(wic)) + 40'sd16384) >>> 15;
    ci_ = ((40'(signed'(yc[15:0])) * 40'(wic) + 40'(signed'(yc[31:16])) * 40'(w2c)) + 40'sd16384) >>> 15;
    tr = br + cr_;
    ti = bi + ci_;
    dr = br - cr_;
    di = bi - ci_;
    ur = 40'(ar) - ((tr + 40'sd1) >>> 1);
    ui = 40'(ai) - ((ti + 40'sd1) >>> 1);
    vr = (dr * 40'sd28378 + 40'sd16384) >>> 15;
    vi = (di * 40'sd28378 + 40'sd16384) >>> 15;
    x0r = 40'(ar) + tr;
    x0i = 40'(ai) + ti;
    if (!cc_inv) begin
      x1r = ur + vi;  x1i = ui - vr;
      x2r = ur - vi;  x2i = ui + vr;
    end else begin
      x1r = ur - vi;  x1i = ui + vr;
      x2r = ur + vi;  x2i = ui - vr;
    end
    cmv = 40'(f_cm(cc_sel[0]));
    s1 = (x0r * cmv + 40'sd8192) >>> 14;
    s2 = (x0i * cmv + 40'sd8192) >>> 14;
    s3 = (x1r * cmv + 40'sd8192) >>> 14;
    s4 = (x1i * cmv + 40'sd8192) >>> 14;
  end
  logic signed [39:0] s5, s6;
  always_comb begin
    s5 = (x2r * cmv + 40'sd8192) >>> 14;
    s6 = (x2i * cmv + 40'sd8192) >>> 14;
  end
  wire [2:0] sat_cnt = 3'(is_sat(s1)) + 3'(is_sat(s2)) + 3'(is_sat(s3)) + 3'(is_sat(s4)) + 3'(is_sat(s5)) + 3'(is_sat(s6));

  // ---------------- output (combinational read) ----------------
  wire  [8:0]  o_m   = f_m(co_sel);
  wire  [8:0]  o_l   = {1'b0, f_l(co_sel)};
  wire  [9:0]  o_n0  = {1'b0, oc} + {1'b0, co_orot};
  wire  [8:0]  o_n   = (o_n0 >= {1'b0, o_m}) ? 9'(o_n0 - {1'b0, o_m}) : o_n0[8:0];
  logic [31:0] o_word;
  always_comb begin
    if (o_n >= {o_l[7:0], 1'b0} + o_l) o_word = 32'd0;      // not reachable (n < M)
    else if (o_n >= {o_l[7:0], 1'b0}) o_word = o2[7'(o_n - {o_l[7:0], 1'b0})];
    else if (o_n >= o_l) o_word = o1[7'(o_n - o_l)];
    else o_word = o0[7'(o_n)];
  end
  assign m_axis_valid = out_act;
  assign m_axis_data  = o_word;
  assign m_axis_last  = out_act & (oc == o_m - 9'd1);

  wire y_start = x_full & ~f_active & ~c_active & ~y_full & ~comb_act;
  wire comb_start = y_full & ~comb_act & ~o_full;
  wire out_start = o_full & ~out_act;
  wire sat_ovf = comb_act;
  assign ovf_cnt = (fft_ovf + own_ovf < fft_ovf) ? 16'hFFFF : fft_ovf + own_ovf;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      icnt <= '0;
      x_full <= 1'b0;
      ci_sel_q <= '0; ci_inv_q <= 1'b0; ci_irot_q <= '0; ci_orot_q <= '0;
      cf_sel <= '0; cf_inv <= 1'b0; cf_orot <= '0;
      cc_sel <= '0; cc_inv <= 1'b0; cc_orot <= '0;
      co_sel <= '0; co_orot <= '0;
      f_active <= 1'b0; fr <= '0; fm <= '0;
      c_active <= 1'b0; y_full <= 1'b0; cr <= '0; ck <= '0;
      comb_act <= 1'b0; kk <= '0; o_full <= 1'b0; out_act <= 1'b0; oc <= '0;
      own_ovf <= '0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      // ---- input ----
      if (in_xfer) begin
        if (i_first) begin
          ci_sel_q <= m_sel;
          ci_inv_q <= inverse;
          ci_irot_q <= in_rot;
          ci_orot_q <= out_rot;
        end
        xmem[i_idx] <= s_axis_data;
        if (s_axis_last != i_lastbeat) err_len <= 1'b1;
        if (i_lastbeat) begin
          icnt <= '0;
          x_full <= 1'b1;
        end else icnt <= icnt + 9'd1;
      end
      // ---- feed ----
      if (y_start) begin
        f_active <= 1'b1;
        c_active <= 1'b1;
        fr <= '0; fm <= '0; cr <= '0; ck <= '0;
        cf_sel <= ci_sel_q; cf_inv <= ci_inv_q; cf_orot <= ci_orot_q;
      end
      if (feed_x) begin
        if (fm == f_lc - 8'd1) begin
          fm <= '0;
          if (fr == 2'd2) begin
            f_active <= 1'b0;
            x_full <= 1'b0;
          end else fr <= fr + 2'd1;
        end else fm <= fm + 8'd1;
      end
      // ---- collect ----
      if (ff_v && c_active) begin
        case (cr)
          2'd0: y0[ck[6:0]] <= ff_d;
          2'd1: y1[ck[6:0]] <= ff_d;
          default: y2[ck[6:0]] <= ff_d;
        endcase
        if (ck == f_lc - 8'd1) begin
          ck <= '0;
          if (cr == 2'd2) begin
            c_active <= 1'b0;
            y_full <= 1'b1;
          end else cr <= cr + 2'd1;
        end else ck <= ck + 8'd1;
      end
      // ---- combine ----
      if (comb_start) begin
        comb_act <= 1'b1;
        kk <= '0;
        cc_sel <= cf_sel; cc_inv <= cf_inv; cc_orot <= cf_orot;
        y_full <= 1'b0;
      end
      if (comb_act) begin
        o0[kk[6:0]] <= {sat16(s2), sat16(s1)};
        o1[kk[6:0]] <= {sat16(s4), sat16(s3)};
        o2[kk[6:0]] <= {sat16(s6), sat16(s5)};
        own_ovf <= (own_ovf + 16'(sat_cnt) < own_ovf) ? 16'hFFFF : own_ovf + 16'(sat_cnt);
        if (kk == cl_c - 8'd1) begin
          comb_act <= 1'b0;
          o_full <= 1'b1;
        end else kk <= kk + 8'd1;
      end
      // ---- output ----
      if (out_start) begin
        out_act <= 1'b1;
        oc <= '0;
        co_sel <= cc_sel; co_orot <= cc_orot;
      end
      if (out_act && m_axis_ready) begin
        if (oc == o_m - 9'd1) begin
          out_act <= 1'b0;
          o_full <= 1'b0;
        end else oc <= oc + 9'd1;
      end
    end
  end
  wire unused_ok = &{1'b0, fft_err, ff_l, sat_ovf, fa10[9]};
endmodule
