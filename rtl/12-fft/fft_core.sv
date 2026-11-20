// fft_core - memory-based radix-2 DIT FFT/IFFT, two ping-pong buffers, one butterfly per clock (design/12-fft.md).
module fft_core #(
    parameter int MAX_LOG2 = 10          // 6..10
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  fft_log2,
    input  logic        inverse,
    input  logic [9:0]  shift_mask,
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
  localparam int AW = MAX_LOG2;
  localparam int SZ = 2**AW;

  logic [31:0] mem0[SZ];
  logic [31:0] mem1[SZ];

  typedef enum logic [1:0] {EMPTY, LOADED, COMPUTING, DONE} mstate_t;
  mstate_t st[2];
  logic [3:0] bank_log2[2];
  logic       bank_inv[2];
  logic [9:0] bank_shift[2];

  function automatic [3:0] clamp_log2(input [3:0] v);
    begin
      if (v < 4'd6) clamp_log2 = 4'd6;
      else if (v > 4'(MAX_LOG2)) clamp_log2 = 4'(MAX_LOG2);
      else clamp_log2 = v;
    end
  endfunction

  function automatic [AW-1:0] bitrev(input [AW-1:0] x, input [3:0] l);
    reg [AW-1:0] r;
    integer i;
    integer li;
    begin
      r = '0;
      li = {28'd0, l};
      for (i = 0; i < AW; i = i + 1) if (i < li) r[li-1-i] = x[i];
      bitrev = r;
    end
  endfunction

  // ---------------- write side ----------------
  logic          wr_bank;
  logic [AW:0]   wr_cnt;
  logic [3:0]    wr_log2_q;
  logic          wr_inv_q;
  logic [9:0]    wr_shift_q;

  wire [3:0]  cur_log2  = (wr_cnt == '0) ? clamp_log2(fft_log2) : wr_log2_q;
  wire        cur_inv   = (wr_cnt == '0) ? inverse : wr_inv_q;
  wire [9:0]  cur_shift = (wr_cnt == '0) ? shift_mask : wr_shift_q;
  wire [AW:0] n_cur     = (AW + 1)'(1) << cur_log2;
  wire        at_last   = (wr_cnt == n_cur - 1'b1);
  wire        wr_ok     = (st[wr_bank] == EMPTY);

  assign s_axis_ready = wr_ok;
  wire wr_xfer = s_axis_valid & wr_ok;
  wire [AW-1:0] wr_addr = bitrev(wr_cnt[AW-1:0], cur_log2);

  // ---------------- engine ----------------
  logic          cb;                 // bank being computed
  logic          running;
  logic [3:0]    stage;              // 1..L
  logic [AW-1:0] bcnt;               // butterfly counter 0..N/2-1
  wire  [3:0]    c_log2  = bank_log2[cb];
  wire           c_inv   = bank_inv[cb];
  wire  [9:0]    c_shift = bank_shift[cb];
  wire  [AW:0]   c_n     = (AW + 1)'(1) << c_log2;
  wire  [AW-1:0] half    = AW'(1) << (stage - 4'd1);
  wire  [AW-1:0] jj      = bcnt & (half - 1'b1);
  wire  [AW-1:0] gg      = bcnt >> (stage - 4'd1);
  wire  [AW-1:0] ia      = (gg << stage) | jj;
  wire  [AW-1:0] ib      = ia | half;
  wire  [8:0]    tw_idx  = 9'(jj << (4'd10 - stage));    // j < 2^(stage-1), so the shifted index is below 512

  wire [31:0] va = cb ? mem1[ia] : mem0[ia];
  wire [31:0] vb = cb ? mem1[ib] : mem0[ib];

  logic [15:0] cosq, sinq;
  fft_twiddle_rom u_rom (.k(tw_idx), .cos_q(cosq), .sin_q(sinq));

  // butterfly arithmetic
  logic signed [15:0] ar, ai, br, bi, wr_, wi_;
  logic signed [32:0] prr, pri;
  logic signed [15:0] pr, pi_;
  logic signed [16:0] sr, si, dr, di;
  logic signed [15:0] o1r, o1i, o2r, o2i;
  logic [2:0]         sat_n;
  logic               do_shift;

  function automatic signed [15:0] sat16(input signed [16:0] v);
    begin
      if (v > 17'sd32767) sat16 = 16'sd32767;
      else if (v < -17'sd32768) sat16 = -16'sd32768;
      else sat16 = v[15:0];
    end
  endfunction

  always_comb begin
    ar = va[15:0];  ai = va[31:16];
    br = vb[15:0];  bi = vb[31:16];
    wr_ = cosq;
    wi_ = c_inv ? $signed(sinq) : -$signed(sinq);
    prr = (33'(br) * 33'(wr_)) - (33'(bi) * 33'(wi_));
    pri = (33'(br) * 33'(wi_)) + (33'(bi) * 33'(wr_));
    prr = prr + 33'sd16384;
    pri = pri + 33'sd16384;
    pr  = sat16(17'(prr >>> 15));
    pi_ = sat16(17'(pri >>> 15));
    sr = 17'(ar) + 17'(pr);
    si = 17'(ai) + 17'(pi_);
    dr = 17'(ar) - 17'(pr);
    di = 17'(ai) - 17'(pi_);
    do_shift = c_shift[stage - 4'd1];
    sat_n = '0;
    if (do_shift) begin
      o1r = 16'((sr + 17'sd1) >>> 1);
      o1i = 16'((si + 17'sd1) >>> 1);
      o2r = 16'((dr + 17'sd1) >>> 1);
      o2i = 16'((di + 17'sd1) >>> 1);
    end else begin
      o1r = sat16(sr); o1i = sat16(si); o2r = sat16(dr); o2i = sat16(di);
      if (sr > 17'sd32767 || sr < -17'sd32768) sat_n = sat_n + 3'd1;
      if (si > 17'sd32767 || si < -17'sd32768) sat_n = sat_n + 3'd1;
      if (dr > 17'sd32767 || dr < -17'sd32768) sat_n = sat_n + 3'd1;
      if (di > 17'sd32767 || di < -17'sd32768) sat_n = sat_n + 3'd1;
    end
  end

  // sat_n can reach 4: use a wider count for the accumulation below
  wire [2:0] unused_sat = sat_n;

  // ---------------- read side ----------------
  logic        rd_bank;
  logic [AW:0] rd_cnt;
  wire  [AW:0] rd_n = (AW + 1)'(1) << bank_log2[rd_bank];
  assign m_axis_valid = (st[rd_bank] == DONE);
  assign m_axis_data  = rd_bank ? mem1[rd_cnt[AW-1:0]] : mem0[rd_cnt[AW-1:0]];
  assign m_axis_last  = (rd_cnt == rd_n - 1'b1);
  wire rd_xfer = m_axis_valid & m_axis_ready;

  // ---------------- memory writes ----------------
  always_ff @(posedge clk) begin
    if (wr_xfer) begin
      if (wr_bank) mem1[wr_addr] <= s_axis_data;
      else mem0[wr_addr] <= s_axis_data;
    end
    if (running) begin
      if (cb) begin
        mem1[ia] <= {o1i, o1r};
        mem1[ib] <= {o2i, o2r};
      end else begin
        mem0[ia] <= {o1i, o1r};
        mem0[ib] <= {o2i, o2r};
      end
    end
  end

  // ---------------- control ----------------
  logic [16:0] ovf_sum;
  always_comb ovf_sum = {1'b0, ovf_cnt} + 17'(sat_n);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      st[0]   <= EMPTY;
      st[1]   <= EMPTY;
      wr_bank <= 1'b0;
      wr_cnt  <= '0;
      cb      <= 1'b0;
      running <= 1'b0;
      stage   <= 4'd1;
      bcnt    <= '0;
      rd_bank <= 1'b0;
      rd_cnt  <= '0;
      ovf_cnt <= '0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      // write side
      if (wr_xfer) begin
        if (wr_cnt == '0) begin
          wr_log2_q  <= cur_log2;
          wr_inv_q   <= cur_inv;
          wr_shift_q <= cur_shift;
        end
        if (s_axis_last != at_last) err_len <= 1'b1;
        if (at_last) begin
          st[wr_bank]         <= LOADED;
          bank_log2[wr_bank]  <= cur_log2;
          bank_inv[wr_bank]   <= cur_inv;
          bank_shift[wr_bank] <= cur_shift;
          wr_bank             <= ~wr_bank;
          wr_cnt              <= '0;
        end else begin
          wr_cnt <= wr_cnt + 1'b1;
        end
      end
      // engine
      if (!running) begin
        if (st[cb] == LOADED) begin
          st[cb]  <= COMPUTING;
          running <= 1'b1;
          stage   <= 4'd1;
          bcnt    <= '0;
        end
      end else begin
        if (do_shift == 1'b0) ovf_cnt <= ovf_sum[16] ? 16'hFFFF : ovf_sum[15:0];
        if (bcnt == AW'((c_n >> 1) - 1'b1)) begin
          bcnt <= '0;
          if (stage == c_log2) begin
            st[cb]  <= DONE;
            running <= 1'b0;
            cb      <= ~cb;
          end else begin
            stage <= stage + 4'd1;
          end
        end else begin
          bcnt <= bcnt + 1'b1;
        end
      end
      // read side
      if (rd_xfer) begin
        if (m_axis_last) begin
          st[rd_bank] <= EMPTY;
          rd_bank     <= ~rd_bank;
          rd_cnt      <= '0;
        end else begin
          rd_cnt <= rd_cnt + 1'b1;
        end
      end
    end
  end

  wire unused_ok = &{1'b0, unused_sat};
endmodule
