// Module 31: DFT-spread receive stage (MMSE weighting, inverse DFT, common phase and gain from the reference symbols).
// Definition: design/31-dft-s-ofdm.md section 4 (bit-exact model: tests/31-dft-s-ofdm/dfts_model.py, dfts_rx).
module dfts_rx (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  fft_log2,          // 6..9, sampled with the first bin of a symbol
    input  logic        ref_boost,         // as at the transmitter (sampled with the first bin)
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [31:0] s_axis_data,       // zero-forcing equalised bin {Q, I}
    input  logic [7:0]  s_csi,             // weight of the bin (module 17), aligned with the data
    input  logic        s_axis_last,       // on bin N-1
    input  logic        lut_we,            // gain table write port: lut[lut_addr] = lut_data (256 = 1.0)
    input  logic [7:0]  lut_addr,
    input  logic [8:0]  lut_data,
    input  logic [7:0]  csi_out,           // csi of the despread symbols (set by firmware)
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic [7:0]  m_csi,
    output logic        m_axis_last,
    output logic [15:0] ovf_cnt,
    output logic        err_len
);
  function automatic [1:0] f_sel(input [3:0] l);
    if (l <= 4'd6) f_sel = 2'd0;
    else if (l == 4'd7) f_sel = 2'd1;
    else if (l == 4'd8) f_sel = 2'd2;
    else f_sel = 2'd3;
  endfunction
  function automatic [8:0] f_m(input [1:0] s);
    f_m = 9'd48 << s;
  endfunction
  function automatic [9:0] f_n(input [1:0] s);
    f_n = 10'd64 << s;
  endfunction
  function automatic signed [15:0] sat16(input signed [47:0] v);
    if (v > 48'sd32767) sat16 = 16'sd32767;
    else if (v < -48'sd32768) sat16 = -16'sd32768;
    else sat16 = v[15:0];
  endfunction

  // ---------------- gain table with initialisation ----------------
  logic [8:0] lut [256];
  logic [8:0] li_q;                                     // initialisation counter (256 entries to 1.0)
  wire        li_done = li_q[8];
  always_ff @(posedge clk) begin
    if (!rst_n) li_q <= '0;
    else if (!li_done) begin
      lut[li_q[7:0]] <= 9'd256;
      li_q <= li_q + 9'd1;
    end else if (lut_we) lut[lut_addr] <= lut_data;
  end

  // ---------------- input ----------------
  logic [9:0] b_q;
  logic [1:0] sel_q;
  wire        first = (b_q == 10'd0);
  wire [1:0]  sel   = first ? f_sel(fft_log2) : sel_q;
  wire [9:0]  n_c   = f_n(sel);
  wire [9:0]  h_c   = {1'b0, f_m(sel) >> 1};
  wire        used  = (b_q != 10'd0) && ((b_q <= h_c) || (b_q >= n_c - h_c));
  logic       d_ready;
  wire        d_valid = s_axis_valid & used & li_done;
  assign s_axis_ready = li_done & (used ? d_ready : 1'b1);
  wire        in_xfer = s_axis_valid & s_axis_ready;
  wire  [8:0] g = lut[s_csi];
  wire signed [47:0] gs = $signed({39'd0, g});
  wire signed [15:0] zr = s_axis_data[15:0];
  wire signed [15:0] zi = s_axis_data[31:16];
  wire signed [47:0] pr = 48'(zr) * gs;
  wire signed [47:0] pi = 48'(zi) * gs;
  wire [31:0] w_data = {sat16((pi + 48'sd128) >>> 8), sat16((pr + 48'sd128) >>> 8)};
  wire        last_bin = (b_q == n_c - 10'd1);

  logic [2:0] ff_mem [4];                              // {boost, sel}
  logic [1:0] ff_wr, ff_rd;
  logic [2:0] ff_cnt;
  wire        ff_push = in_xfer & first;
  logic       col_done;

  logic        dm_valid, dm_ready, dm_last;
  logic [31:0] dm_data;
  logic        dm_err;
  dft_mixed u_dft (
      .clk(clk), .rst_n(rst_n), .m_sel(sel), .inverse(1'b1), .in_rot(h_c[8:0]), .out_rot(9'd0),
      .s_axis_valid(d_valid), .s_axis_ready(d_ready), .s_axis_data(w_data), .s_axis_last(last_bin),
      .m_axis_valid(dm_valid), .m_axis_ready(dm_ready), .m_axis_data(dm_data), .m_axis_last(dm_last),
      .ovf_cnt(ovf_cnt), .err_len(dm_err));

  // ---------------- collector, reference accumulation ----------------
  logic [31:0] dbuf [384];
  logic        full_q;
  logic [8:0]  cn_q;
  logic [5:0]  cpc_q;
  logic [2:0]  cjc_q;
  logic signed [23:0] cs_i, cs_q;
  wire  [1:0]  c_sel = ff_mem[ff_rd][1:0];
  wire  [8:0]  c_m   = f_m(c_sel);
  wire  [5:0]  c_g   = 6'd6 << c_sel;
  wire         c_ref = (cpc_q == (c_g >> 1));
  logic [7:0]  refsign;
  assign refsign = 8'b11010010;
  assign dm_ready = ~full_q & (ff_cnt != 3'd0);
  wire c_xfer = dm_valid & dm_ready;
  wire signed [15:0] dm_i = dm_data[15:0];
  wire signed [15:0] dm_q = dm_data[31:16];
  assign col_done = c_xfer & (cn_q == c_m - 9'd1);

  // ---------------- common correction: c = csum / R, g = 1 / c ----------------
  logic        o_boost_q;
  wire signed [39:0] rn_s  = o_boost_q ? 40'sd4096 : 40'sd8192;
  wire signed [39:0] pcs_i = 40'(cs_i) * rn_s;
  wire signed [39:0] pcs_q = 40'(cs_q) * rn_s;
  wire signed [15:0] c_i = sat16(48'((pcs_i + 40'sd32768) >>> 16));
  wire signed [15:0] c_q = sat16(48'((pcs_q + 40'sd32768) >>> 16));
  wire [31:0] cpow = 32'(c_i * c_i) + 32'(c_q * c_q);
  logic [7:0]  r_idx;
  logic [15:0] r_t;
  logic [4:0]  r_p;
  logic [31:0] r_out;
  recip_rom u_rom (.idx(r_idx), .t(r_t));
  always_comb begin
    r_p = 5'd0;
    for (int i = 0; i < 32; i++) if (cpow[i]) r_p = 5'(i);
    if (r_p >= 5'd8) r_idx = 8'((cpow >> (r_p - 5'd8)) - 32'd256);
    else r_idx = 8'((cpow << (5'd8 - r_p)) - 32'd256);
    if (cpow == 32'd0) r_out = 32'h7FFFFFFF;
    else if (r_p <= 5'd25) begin
      if ((64'(r_t) << (5'd25 - r_p)) > 64'h7FFFFFFF) r_out = 32'h7FFFFFFF;
      else r_out = 32'(64'(r_t) << (5'd25 - r_p));
    end else r_out = 32'(r_t >> (r_p - 5'd25));
  end
  wire signed [32:0] r_s = $signed({1'b0, r_out});
  wire signed [48:0] pg_i = c_i * r_s;
  wire signed [48:0] pg_q = -(c_q * r_s);
  logic signed [15:0] g_i, g_q;
  logic        calc_q;                                 // one clock between the last reference and the output

  // ---------------- output ----------------
  logic        oact_q;
  logic [8:0]  on_q;
  logic [5:0]  opc_q;
  logic [2:0]  ojc_q;
  logic [1:0]  o_sel_q;
  wire  [8:0]  o_m   = f_m(o_sel_q);
  wire  [5:0]  o_g   = 6'd6 << o_sel_q;
  wire         o_ref = (opc_q == (o_g >> 1));
  wire  [31:0] o_word = dbuf[on_q];
  wire signed [15:0] wi = o_word[15:0];
  wire signed [15:0] wq = o_word[31:16];
  wire signed [47:0] zr_p = 48'(wi) * 48'(g_i) - 48'(wq) * 48'(g_q);
  wire signed [47:0] zi_p = 48'(wi) * 48'(g_q) + 48'(wq) * 48'(g_i);
  assign m_axis_valid = oact_q & ~o_ref;
  assign m_axis_data  = {sat16((zi_p + 48'sd2048) >>> 12), sat16((zr_p + 48'sd2048) >>> 12)};
  assign m_csi        = csi_out;
  assign m_axis_last  = m_axis_valid & (on_q == o_m - 9'd1);
  wire   o_adv = oact_q & (o_ref | m_axis_ready);
  wire   o_end = o_adv & (on_q == o_m - 9'd1);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      b_q <= '0;
      sel_q <= '0;
      ff_wr <= '0;
      ff_rd <= '0;
      ff_cnt <= '0;
      full_q <= 1'b0;
      cn_q <= '0;
      cpc_q <= '0;
      cjc_q <= '0;
      cs_i <= '0;
      cs_q <= '0;
      calc_q <= 1'b0;
      g_i <= '0;
      g_q <= '0;
      oact_q <= 1'b0;
      on_q <= '0;
      opc_q <= '0;
      ojc_q <= '0;
      o_sel_q <= '0;
      o_boost_q <= 1'b0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      // input
      if (in_xfer) begin
        if (first) sel_q <= sel;
        if (s_axis_last != last_bin) err_len <= 1'b1;
        if (last_bin) b_q <= '0;
        else b_q <= b_q + 10'd1;
      end
      if (ff_push) begin
        ff_mem[ff_wr] <= {ref_boost, sel};
        ff_wr <= ff_wr + 2'd1;
      end
      ff_cnt <= ff_cnt + {2'b00, ff_push} - {2'b00, col_done};
      // collector
      if (c_xfer) begin
        dbuf[cn_q] <= dm_data;
        if (c_ref) begin
          if (refsign[cjc_q]) begin
            cs_i <= cs_i - 24'(dm_i);
            cs_q <= cs_q - 24'(dm_q);
          end else begin
            cs_i <= cs_i + 24'(dm_i);
            cs_q <= cs_q + 24'(dm_q);
          end
        end
        if (cn_q == c_m - 9'd1) begin
          cn_q <= '0;
          cpc_q <= '0;
          cjc_q <= '0;
        end else begin
          cn_q <= cn_q + 9'd1;
          if (cpc_q == c_g - 6'd1) begin
            cpc_q <= '0;
            cjc_q <= cjc_q + 3'd1;
          end else cpc_q <= cpc_q + 6'd1;
        end
      end
      if (col_done) begin
        full_q <= 1'b1;
        calc_q <= 1'b1;
        ff_rd <= ff_rd + 2'd1;
        o_sel_q <= c_sel;
        o_boost_q <= ff_mem[ff_rd][2];
      end
      if (calc_q) begin
        calc_q <= 1'b0;
        g_i <= sat16(48'((pg_i + 49'sd32768) >>> 16));
        g_q <= sat16(48'((pg_q + 49'sd32768) >>> 16));
        oact_q <= 1'b1;
        on_q <= '0;
        opc_q <= '0;
        ojc_q <= '0;
        cs_i <= '0;
        cs_q <= '0;
      end
      // output
      if (o_adv) begin
        if (o_end) begin
          oact_q <= 1'b0;
          full_q <= 1'b0;
        end else begin
          on_q <= on_q + 9'd1;
          if (opc_q == o_g - 6'd1) begin
            opc_q <= '0;
            ojc_q <= ojc_q + 3'd1;
          end else opc_q <= opc_q + 6'd1;
        end
      end
    end
  end
  wire unused_ok = &{1'b0, dm_last, dm_err, ojc_q};
endmodule
