// Module 31: DFT-spread transmit stage. M - 8 mapper samples per symbol in, the N bins of the symbol (bin order) out.
// Definition: design/31-dft-s-ofdm.md section 3 (bit-exact model: tests/31-dft-s-ofdm/dfts_model.py, dfts_tx).
module dfts_tx (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  fft_log2,          // 6..9, sampled with the first sample of a symbol
    input  logic        ref_boost,         // 1: reference symbols at twice the data amplitude (sampled with the first sample)
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

  // ---------------- input: reference symbols inserted ----------------
  logic [8:0] n_q;                 // position in the symbol vector
  logic [5:0] pc_q;                // position in the group of M/8
  logic [2:0] jc_q;                // group index
  logic [1:0] sel_q;
  logic       boost_q;
  wire        first  = (n_q == 9'd0);
  wire        boost  = first ? ref_boost : boost_q;
  wire [1:0]  sel    = first ? f_sel(fft_log2) : sel_q;
  wire [8:0]  m_c    = f_m(sel);
  wire [5:0]  g_c    = 6'd6 << sel;                 // group size M/8
  wire        is_ref = (pc_q == (g_c >> 1));
  logic       d_ready, d_valid, d_last;
  logic [31:0] d_data;
  logic [7:0] refsign;
  assign refsign = 8'b11010010;                      // bit j = 1: negative reference (signs +,-,+,+,-,+,-,-)
  wire [15:0] ref_i = refsign[jc_q] ? (boost ? 16'hE000 : 16'hF000) : (boost ? 16'h2000 : 16'h1000);   // -/+ 4096 or 8192
  assign d_valid = is_ref ? 1'b1 : s_axis_valid;
  assign d_data  = is_ref ? {16'h0000, ref_i} : s_axis_data;
  assign d_last  = (n_q == m_c - 9'd1);
  assign s_axis_ready = ~is_ref & d_ready;
  wire d_xfer = d_valid & d_ready;
  wire in_xfer = s_axis_valid & s_axis_ready;

  // configuration FIFO towards the output side
  logic [1:0] ff_mem [4];
  logic [1:0] ff_wr, ff_rd;
  logic [2:0] ff_cnt;
  wire        ff_push = d_xfer & first;
  logic       ob_act;
  logic [9:0] bcnt;
  logic       ob_done;

  logic        dm_valid, dm_ready;
  logic [31:0] dm_data;
  logic        dm_last, dm_err;
  dft_mixed u_dft (
      .clk(clk), .rst_n(rst_n), .m_sel(sel), .inverse(1'b0), .in_rot(9'd0), .out_rot(m_c >> 1),
      .s_axis_valid(d_valid), .s_axis_ready(d_ready), .s_axis_data(d_data), .s_axis_last(d_last),
      .m_axis_valid(dm_valid), .m_axis_ready(dm_ready), .m_axis_data(dm_data), .m_axis_last(dm_last),
      .ovf_cnt(ovf_cnt), .err_len(dm_err));

  // ---------------- output: bins in bin order ----------------
  wire [1:0]  o_sel = ff_mem[ff_rd];
  wire [9:0]  o_n   = f_n(o_sel);
  wire [9:0]  o_h   = {1'b0, f_m(o_sel) >> 1};
  wire        zero_bin = (bcnt == 10'd0) || ((bcnt > o_h) && (bcnt < o_n - o_h));
  wire        o_start = ~ob_act & (ff_cnt != 3'd0) & dm_valid;
  assign m_axis_valid = ob_act & (zero_bin | dm_valid);
  assign m_axis_data  = zero_bin ? 32'd0 : dm_data;
  assign m_axis_last  = ob_act & (bcnt == o_n - 10'd1);
  assign dm_ready     = ob_act & ~zero_bin & m_axis_ready;
  wire o_xfer = m_axis_valid & m_axis_ready;
  assign ob_done = o_xfer & m_axis_last;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      n_q <= '0;
      pc_q <= '0;
      jc_q <= '0;
      sel_q <= '0;
      boost_q <= 1'b0;
      ff_wr <= '0;
      ff_rd <= '0;
      ff_cnt <= '0;
      ob_act <= 1'b0;
      bcnt <= '0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      if (d_xfer) begin
        if (first) begin
          sel_q <= sel;
          boost_q <= ref_boost;
        end
        if (d_last) begin
          n_q <= '0;
          pc_q <= '0;
          jc_q <= '0;
        end else begin
          n_q <= n_q + 9'd1;
          if (pc_q == g_c - 6'd1) begin
            pc_q <= '0;
            jc_q <= jc_q + 3'd1;
          end else pc_q <= pc_q + 6'd1;
        end
      end
      if (in_xfer && (s_axis_last != d_last)) err_len <= 1'b1;
      if (ff_push) begin
        ff_mem[ff_wr] <= sel;
        ff_wr <= ff_wr + 2'd1;
      end
      if (o_start) begin
        ob_act <= 1'b1;
        bcnt <= '0;
      end
      if (o_xfer && !m_axis_last) bcnt <= bcnt + 10'd1;
      if (ob_done) begin
        ob_act <= 1'b0;
        ff_rd <= ff_rd + 2'd1;
      end
      ff_cnt <= ff_cnt + {2'b00, ff_push} - {2'b00, ob_done};
    end
  end
  wire unused_ok = &{1'b0, dm_last, dm_err};
endmodule
