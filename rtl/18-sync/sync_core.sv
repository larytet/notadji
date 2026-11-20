// sync_core - delay-and-correlate burst detection, coarse CFO, derotation, STF end marker, AGC monitor (design/18-sync.md).
module sync_core #(
    parameter int MAX_LOG2 = 9
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  fft_log2,
    input  logic [1:0]  thr_sel,
    input  logic [31:0] min_power,
    input  logic [31:0] agc_lo,
    input  logic [31:0] agc_hi,
    input  logic        rearm,
    input  logic        s_valid,
    input  logic [31:0] s_data,        // {Q, I}
    output logic        m_valid,
    output logic [31:0] m_data,
    output logic        det,
    output logic signed [23:0] cfo_inc,
    output logic [15:0] cfo_angle,
    output logic        fall,
    output logic [7:0]  k_back,
    output logic        metric_ok,
    output logic        agc_up,
    output logic        agc_down,
    output logic        locked
);
  localparam int PM = MAX_LOG2 - 2;          // log2 of the largest P
  localparam int SZ = 2 ** (PM + 2);         // delay line: 2P plus margin

  wire [3:0] l_cl = (fft_log2 < 4'd6) ? 4'd6 : (fft_log2 > 4'(MAX_LOG2)) ? 4'(MAX_LOG2) : fft_log2;
  wire [3:0] pl   = l_cl - 4'd2;             // log2 P
  wire [PM+1:0] pp = (PM + 2)'(1) << pl;      // P
  assign k_back = 8'(pp >> 2);

  // ---------------- delay line ----------------
  logic [31:0] buf_[SZ];
  logic [PM+1:0] wp;
  wire [PM+1:0] ip   = wp - pp;
  wire [PM+1:0] i2p  = wp - pp - pp;
  // samples older than the reset are treated as zero (the delay line is not cleared, the running sums start at zero)
  logic [PM+2:0] fillc;
  wire [31:0] dp   = (fillc >= {1'b0, pp}) ? buf_[ip] : 32'd0;
  wire [31:0] d2p  = (fillc >= {pp, 1'b0}) ? buf_[i2p] : 32'd0;

  wire signed [15:0] ci = s_data[15:0],  cq = s_data[31:16];
  wire signed [15:0] di = dp[15:0],      dq = dp[31:16];
  wire signed [15:0] ei = d2p[15:0],     eq = d2p[31:16];

  // r[n] conj(r[n-P]) and r[n-P] conj(r[n-2P])
  wire signed [32:0] t1i = 33'(ci * di) + 33'(cq * dq);
  wire signed [32:0] t1q = 33'(cq * di) - 33'(ci * dq);
  wire signed [32:0] t0i = 33'(di * ei) + 33'(dq * eq);
  wire signed [32:0] t0q = 33'(dq * ei) - 33'(di * eq);
  wire [31:0] pw_c = 32'(ci * ci) + 32'(cq * cq);
  wire [31:0] pw_d = 32'(di * di) + 32'(dq * dq);
  wire [31:0] pw_e = 32'(ei * ei) + 32'(eq * eq);

  logic signed [39:0] cs_i, cs_q;
  logic        [39:0] es, el;                 // energy of the current window and of the lagged window (P samples earlier)
  wire signed [39:0] cn_i = cs_i + 40'(t1i) - 40'(t0i);
  wire signed [39:0] cn_q = cs_q + 40'(t1q) - 40'(t0q);
  wire        [39:0] en   = es + 40'(pw_c) - 40'(pw_d);
  wire        [39:0] eln  = el + 40'(pw_d) - 40'(pw_e);

  // ---------------- metric (evaluated on the running sums after the update) ----------------
  // normalisation shift from the largest of E and the two components of C (|C| can exceed E when the power drops)
  wire [39:0] nm = en | eln | (cn_i ^ {40{cn_i[39]}}) | (cn_q ^ {40{cn_q[39]}});
  logic [5:0] sh;
  always_comb begin
    sh = 6'd0;
    for (int i = 0; i < 40; i++) if (nm[i]) sh = (i > 19) ? 6'(i - 19) : 6'd0;
  end
  wire signed [39:0] cni_f = cn_i >>> sh;
  wire signed [39:0] cnq_f = cn_q >>> sh;
  wire        [39:0] enn_f = en >> sh;
  wire        [39:0] ell_f = eln >> sh;
  // after the normalisation the operands fit in 21 bits: keep the products narrow
  wire signed [21:0] cni = cni_f[21:0];
  wire signed [21:0] cnq = cnq_f[21:0];
  wire        [20:0] enn = enn_f[20:0];
  wire        [20:0] ell = ell_f[20:0];
  wire [47:0] c2 = 48'(cni * cni) + 48'(cnq * cnq);
  wire [47:0] e2 = 48'(enn * ell);            // E_cur x E_lag: the metric is |C|^2 / (E_cur E_lag)
  logic [47:0] lhs, rhs;
  always_comb begin
    case (thr_sel)
      2'd1:    begin lhs = c2 << 2; rhs = e2; end            // M > 1/4
      2'd2:    begin lhs = c2 << 2; rhs = e2 * 3; end        // M > 3/4
      default: begin lhs = c2 << 1; rhs = e2; end            // M > 1/2
    endcase
  end
  wire mok = (lhs > rhs) && (en > {8'd0, min_power});
  assign metric_ok = mok;

  // ---------------- cordic ----------------
  logic        cd_start, cd_busy, cd_done;
  logic [15:0] cd_angle;
  logic signed [23:0] cx, cy;
  cordic_vec u_cd (.clk(clk), .rst_n(rst_n), .start(cd_start), .x(cx), .y(cy), .busy(cd_busy), .done(cd_done), .angle(cd_angle));

  // ---------------- detector state machine ----------------
  typedef enum logic [1:0] {S_SEARCH, S_PLATEAU, S_DONE} state_t;
  state_t state;
  logic [PM+1:0] ok_cnt, hold_cnt;
  logic [1:0]    low_cnt;
  logic          have_cfo;
  logic [23:0]   ph;
  logic signed [23:0] inc_q;

  assign cfo_inc = inc_q;
  assign locked  = (state != S_SEARCH);
  wire [PM+1:0] conf_len = pp >> 1;

  // CORDIC input: snapshot of the sums, normalised to 23 bits
  logic [5:0] csh;
  always_comb begin
    csh = 6'd0;
    for (int i = 0; i < 40; i++) if (cn_i[i] ^ cn_i[39] || cn_q[i] ^ cn_q[39]) csh = (i > 21) ? 6'(i - 21) : 6'd0;
  end

  // ---------------- AGC monitor ----------------
  logic [PM+1:0] agc_cnt;
  wire [39:0] pavg = en >> pl;

  // ---------------- NCO and rotation ----------------
  wire [9:0] pidx = ph[23:14];
  logic signed [15:0] cs, sn;
  logic [15:0] rc, rs;
  fft_twiddle_rom u_rom (.k(pidx[8:0]), .cos_q(rc), .sin_q(rs));
  always_comb begin
    if (pidx[9]) begin cs = -$signed(rc); sn = -$signed(rs); end
    else begin cs = $signed(rc); sn = $signed(rs); end
  end
  wire signed [31:0] r1 = ci * cs, r2 = cq * sn, r3 = ci * sn, r4 = cq * cs;
  function automatic signed [15:0] sat(input signed [47:0] v);
    begin
      if (v > 48'sd32767) sat = 16'sd32767;
      else if (v < -48'sd32768) sat = -16'sd32768;
      else sat = v[15:0];
    end
  endfunction
  wire signed [15:0] oi = sat((48'(r1) - 48'(r2) + 48'sd16384) >>> 15);
  wire signed [15:0] oq = sat((48'(r3) + 48'(r4) + 48'sd16384) >>> 15);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wp       <= '0;
      fillc    <= '0;
      cs_i     <= '0;
      cs_q     <= '0;
      es       <= '0;
      el       <= '0;
      state    <= S_SEARCH;
      ok_cnt   <= '0;
      hold_cnt <= '0;
      low_cnt  <= '0;
      have_cfo <= 1'b0;
      det      <= 1'b0;
      fall     <= 1'b0;
      cd_start <= 1'b0;
      ph       <= '0;
      inc_q    <= '0;
      cfo_angle <= '0;
      agc_up   <= 1'b0;
      agc_down <= 1'b0;
      agc_cnt  <= '0;
      m_valid  <= 1'b0;
    end else begin
      det      <= 1'b0;
      fall     <= 1'b0;
      cd_start <= 1'b0;
      agc_up   <= 1'b0;
      agc_down <= 1'b0;
      m_valid  <= s_valid;
      if (rearm) begin
        state    <= S_SEARCH;
        ok_cnt   <= '0;
        hold_cnt <= '0;
        low_cnt  <= '0;
        have_cfo <= 1'b0;
        ph       <= '0;
        inc_q    <= '0;
      end
      if (cd_done) begin
        cfo_angle <= cd_angle;
        // step = angle / P in 2^24 = 2 pi units: (angle << 8) >> log2 P, signed
        inc_q     <= $signed({cd_angle, 8'd0}) >>> pl;
        have_cfo  <= 1'b1;
      end
      if (s_valid) begin
        buf_[wp] <= s_data;
        wp       <= wp + 1'b1;
        if (!fillc[PM+2]) fillc <= fillc + 1'b1;
        cs_i     <= cn_i;
        cs_q     <= cn_q;
        es       <= en;
        el       <= eln;
        m_data   <= {oq, oi};
        if (have_cfo || state != S_SEARCH) ph <= ph - 24'(inc_q);
        // AGC monitor: every P samples
        if (agc_cnt == pp - 1'b1) begin
          agc_cnt <= '0;
          if (pavg < {8'd0, agc_lo}) agc_up <= 1'b1;
          else if (pavg > {8'd0, agc_hi}) agc_down <= 1'b1;
        end else agc_cnt <= agc_cnt + 1'b1;
        case (state)
          S_SEARCH: begin
            if (mok) begin
              if (ok_cnt + 1'b1 >= conf_len) begin
                det      <= 1'b1;
                state    <= S_PLATEAU;
                hold_cnt <= '0;
                low_cnt  <= '0;
                cx       <= 24'(cn_i >>> csh);
                cy       <= 24'(cn_q >>> csh);
                cd_start <= 1'b1;
                ph       <= '0;
              end
              ok_cnt <= ok_cnt + 1'b1;
            end else ok_cnt <= '0;
          end
          S_PLATEAU: begin
            hold_cnt <= hold_cnt + 1'b1;
            if (hold_cnt >= conf_len) begin
              if (!mok) begin
                if (low_cnt == 2'd1) begin
                  fall  <= 1'b1;
                  state <= S_DONE;
                end
                low_cnt <= low_cnt + 2'd1;
              end else low_cnt <= '0;
            end
          end
          default: ;
        endcase
      end
    end
  end

  wire unused_ok = &{1'b0, cd_busy, es[39:39], cni_f[39:22], cnq_f[39:22], enn_f[39:21], ell_f[39:21], el[39:39]};
endmodule
