// equalizer - LTF channel estimate, one-tap zero forcing, common phase/gain tracking from pilots (design/17-equalizer.md).
module equalizer #(
    parameter int MAX_LOG2 = 9
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  fft_log2,
    input  logic [1:0]  kind,           // 0 LTF1, 1 LTF2, 2 first data symbol, 3 later data symbol
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [31:0] s_axis_data,    // {Q, I}
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic [7:0]  m_csi,
    output logic        m_axis_last,
    output logic        err_len
);
  localparam int AW = MAX_LOG2;
  localparam int SZ = 2**AW;

  typedef enum logic [2:0] {S_IDLE, S_CMD, S_RX, S_CALC, S_CPE, S_OUT} state_t;
  state_t state;

  logic [1:0]  kind_q;
  logic [3:0]  l_q;
  logic [AW:0] b;                       // bin counter
  logic [AW-1:0] lastd;                 // last data bin of the symbol

  // memories
  logic [35:0] hm[SZ];                  // LTF sum {Q18, I18}
  logic [1:0]  tm[SZ];                  // {sign, used}
  logic [31:0] gm[SZ];                  // G {Q16, I16}
  logic [7:0]  cm[SZ];                  // csi
  logic [31:0] wm[SZ];                  // W {Q16, I16}
  logic [1:0]  td[SZ];                  // tone type of the data symbol

  // ---------------- tone plan from module 7 ----------------
  logic        cmd_valid, cmd_ready, pg_v, pg_l;
  logic [33:0] pg_d;
  wire  [1:0]  cmd_kind = (kind_q < 2'd2) ? 2'd1 : 2'd2;
  assign cmd_valid = (state == S_CMD);
  preamble_gen u_pg (
      .clk(clk), .rst_n(rst_n),
      .cmd_valid(cmd_valid), .cmd_ready(cmd_ready), .cmd_kind(cmd_kind), .cmd_log2(l_q), .cmd_frame_start(kind_q == 2'd2),
      .m_axis_valid(pg_v), .m_axis_ready((state == S_RX) & s_axis_valid), .m_axis_data(pg_d), .m_axis_last(pg_l));

  wire        rx_xfer = (state == S_RX) & s_axis_valid & pg_v;
  assign s_axis_ready = (state == S_RX) & pg_v;

  wire [1:0]  pt = pg_d[33:32];
  wire        sg = pg_d[15];

  // ---------------- arithmetic helpers ----------------
  function automatic signed [15:0] sat16(input signed [63:0] v);
    begin
      if (v > 64'sd32767) sat16 = 16'sd32767;
      else if (v < -64'sd32768) sat16 = -16'sd32768;
      else sat16 = v[15:0];
    end
  endfunction

  // shared reciprocal unit: r = approx 2^40 / x (see design section 1 step 2)
  logic [31:0] rx_in;
  logic [7:0]  r_idx;
  logic [15:0] r_t;
  logic [4:0]  r_p;
  logic [31:0] r_out;
  recip_rom u_rom (.idx(r_idx), .t(r_t));
  always_comb begin
    r_p = 5'd0;
    for (int i = 0; i < 32; i++) if (rx_in[i]) r_p = 5'(i);
    if (r_p >= 5'd8) r_idx = 8'((rx_in >> (r_p - 5'd8)) - 32'd256);
    else r_idx = 8'((rx_in << (5'd8 - r_p)) - 32'd256);
    if (rx_in == 32'd0) r_out = 32'h7FFFFFFF;
    else if (r_p <= 5'd25) begin
      if ((64'(r_t) << (5'd25 - r_p)) > 64'h7FFFFFFF) r_out = 32'h7FFFFFFF;
      else r_out = 32'(64'(r_t) << (5'd25 - r_p));
    end else r_out = 32'(r_t >> (r_p - 5'd25));
  end

  // ---------------- CALC: coefficient of bin b ----------------
  wire signed [17:0] hsi = hm[b[AW-1:0]][17:0];
  wire signed [17:0] hsq = hm[b[AW-1:0]][35:18];
  wire               hsg = tm[b[AW-1:0]][1];
  wire signed [18:0] hvi = hsg ? -{hsi[17], hsi} : {hsi[17], hsi};
  wire signed [18:0] hvq = hsg ? -{hsq[17], hsq} : {hsq[17], hsq};
  wire signed [15:0] hri = sat16(64'(($signed(hvi) + 19'sd1) >>> 1));
  wire signed [15:0] hrq = sat16(64'(($signed(hvq) + 19'sd1) >>> 1));
  wire [31:0] hpow = 32'(hri * hri) + 32'(hrq * hrq);

  // ---------------- CPE: common correction ----------------
  logic signed [23:0] csum_i, csum_q;
  logic [14:0] rn;
  always_comb begin
    case (l_q)
      4'd6: rn = 15'd16384;
      4'd7: rn = 15'd10923;
      4'd8: rn = 15'd8192;
      default: rn = 15'd4096;
    endcase
  end
  wire signed [15:0] rn_s = $signed({1'b0, rn});       // unsigned operands would make the products unsigned: keep everything signed
  wire signed [39:0] pcs_i = csum_i * rn_s;            // 24 x 16 bit
  wire signed [39:0] pcs_q = csum_q * rn_s;
  wire signed [15:0] c_i = sat16((64'(pcs_i) + 64'sd32768) >>> 16);
  wire signed [15:0] c_q = sat16((64'(pcs_q) + 64'sd32768) >>> 16);
  wire [31:0] cpow = 32'(c_i * c_i) + 32'(c_q * c_q);
  logic signed [15:0] g_i, g_q;

  assign rx_in = (state == S_CALC) ? hpow : cpow;
  wire signed [32:0] r_s = $signed({1'b0, r_out});     // non-negative, kept signed so that the products stay signed
  wire signed [48:0] pg_i = hri * r_s;                  // 16 x 33 bit
  wire signed [48:0] pg_q = -(hrq * r_s);
  wire signed [48:0] pc_i = c_i * r_s;
  wire signed [48:0] pc_q = -(c_q * r_s);

  // ---------------- data pass 1: W = Y G ----------------
  wire signed [15:0] y_i = s_axis_data[15:0];
  wire signed [15:0] y_q = s_axis_data[31:16];
  wire signed [15:0] g_bi = gm[b[AW-1:0]][15:0];
  wire signed [15:0] g_bq = gm[b[AW-1:0]][31:16];
  wire signed [31:0] m1 = y_i * g_bi, m2 = y_q * g_bq, m3 = y_i * g_bq, m4 = y_q * g_bi;
  wire signed [15:0] w_i = sat16((64'(m1) - 64'(m2) + 64'sd2048) >>> 12);
  wire signed [15:0] w_q = sat16((64'(m3) + 64'(m4) + 64'sd2048) >>> 12);

  // ---------------- output pass: Z = W g ----------------
  wire signed [15:0] ws_i = wm[b[AW-1:0]][15:0];
  wire signed [15:0] ws_q = wm[b[AW-1:0]][31:16];
  wire signed [31:0] n1 = ws_i * g_i, n2 = ws_q * g_q, n3 = ws_i * g_q, n4 = ws_q * g_i;
  wire signed [15:0] z_i = sat16((64'(n1) - 64'(n2) + 64'sd2048) >>> 12);
  wire signed [15:0] z_q = sat16((64'(n3) + 64'(n4) + 64'sd2048) >>> 12);

  wire is_data_bin = (state == S_OUT) && (td[b[AW-1:0]] == 2'd1);
  assign m_axis_valid = is_data_bin;
  assign m_axis_data  = {z_q, z_i};
  assign m_csi        = cm[b[AW-1:0]];
  assign m_axis_last  = is_data_bin && (b[AW-1:0] == lastd);

  wire [AW:0] n_bins = (AW + 1)'(1) << l_q;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state   <= S_IDLE;
      b       <= '0;
      csum_i  <= '0;
      csum_q  <= '0;
      lastd   <= '0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      case (state)
        S_IDLE: if (s_axis_valid) begin
          kind_q <= kind;
          l_q    <= (fft_log2 < 4'd6) ? 4'd6 : (fft_log2 > 4'(MAX_LOG2)) ? 4'(MAX_LOG2) : fft_log2;
          state  <= S_CMD;
        end
        S_CMD: if (cmd_ready) begin
          b     <= '0;
          state <= S_RX;
        end
        S_RX: if (rx_xfer) begin
          if (pg_l != s_axis_last) err_len <= 1'b1;
          b <= b + 1'b1;
          case (kind_q)
            2'd0: begin
              tm[b[AW-1:0]] <= {sg, (pt != 2'd0)};
              hm[b[AW-1:0]] <= {{2{y_q[15]}}, y_q, {2{y_i[15]}}, y_i};
            end
            2'd1: if (tm[b[AW-1:0]][0]) begin
              hm[b[AW-1:0]] <= {hsq + {{2{y_q[15]}}, y_q}, hsi + {{2{y_i[15]}}, y_i}};
            end
            default: begin
              td[b[AW-1:0]] <= pt;
              if (pt != 2'd0) begin
                wm[b[AW-1:0]] <= {w_q, w_i};
                if (pt == 2'd2) begin
                  csum_i <= sg ? csum_i - 24'(w_i) : csum_i + 24'(w_i);
                  csum_q <= sg ? csum_q - 24'(w_q) : csum_q + 24'(w_q);
                end
                if (pt == 2'd1) lastd <= b[AW-1:0];
              end
            end
          endcase
          if (pg_l) begin
            b <= '0;
            state <= (kind_q == 2'd0) ? S_IDLE : (kind_q == 2'd1) ? S_CALC : S_CPE;
          end
        end
        S_CALC: begin
          if (tm[b[AW-1:0]][0]) begin
            gm[b[AW-1:0]] <= {sat16((64'(pg_q) + 64'sd32768) >>> 16), sat16((64'(pg_i) + 64'sd32768) >>> 16)};
            cm[b[AW-1:0]] <= (hpow >> 17 > 32'd255) ? 8'd255 : 8'(hpow >> 17);
          end else begin
            gm[b[AW-1:0]] <= 32'd0;
            cm[b[AW-1:0]] <= 8'd0;
          end
          if (b == n_bins - 1'b1) begin
            b     <= '0;
            state <= S_IDLE;
          end else b <= b + 1'b1;
        end
        S_CPE: begin
          g_i    <= sat16((64'(pc_i) + 64'sd32768) >>> 16);
          g_q    <= sat16((64'(pc_q) + 64'sd32768) >>> 16);
          csum_i <= '0;
          csum_q <= '0;
          b      <= '0;
          state  <= S_OUT;
        end
        default: begin     // S_OUT
          if (is_data_bin) begin
            if (m_axis_ready) begin
              if (b[AW-1:0] == lastd) begin
                b     <= '0;
                state <= S_IDLE;
              end else b <= b + 1'b1;
            end
          end else b <= b + 1'b1;
        end
      endcase
    end
  end
  wire unused_ok = &{1'b0, pg_d[31:16], pg_d[14:0]};
endmodule
