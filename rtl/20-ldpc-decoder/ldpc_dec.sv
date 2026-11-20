// ldpc_dec - layered normalised min-sum LDPC decoder, Z rows in parallel (design/20-ldpc-decoder.md).
module ldpc_dec (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [2:0]  code,
    input  logic [5:0]  max_iter,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic signed [7:0] s_axis_data,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic        m_axis_last,
    output logic        m_ok,
    output logic [5:0]  m_iters,
    output logic        err_len
);
  typedef enum logic [3:0] {S_LOAD, S_BUILD, S_PRE, S_LINIT, S_PA, S_PB, S_LEND, S_IEND, S_OUT} state_t;
  state_t state;

  // ---------------- code parameters ----------------
  logic [2:0] code_q, built_code;
  logic       built_v;
  logic [5:0] maxit_q;
  logic [2:0] code_sel;
  logic       rom_valid;
  logic [6:0] rom_shift, z_rom, xs_rom;
  logic [3:0] mb_rom, bi;
  logic [4:0] kb_rom, bc;
  ldpc_code_rom u_rom (.code(code_sel), .row(bi), .col(bc), .valid(rom_valid), .shift(rom_shift),
                       .z(z_rom), .mb(mb_rom), .kb(kb_rom), .xs(xs_rom));

  logic [10:0] ncnt;                        // LLR index while loading
  logic [6:0]  bidx;
  logic [4:0]  blkidx;
  wire         first_llr = (state == S_LOAD) && (ncnt == 11'd0);
  assign code_sel = first_llr ? code : code_q;
  wire [10:0]  n_tot = 11'd24 * 11'(z_rom);
  wire [10:0]  k_tot = 11'(kb_rom) * 11'(z_rom);

  // ---------------- state ----------------
  logic signed [8:0] post [24][81];                    // posterior: 9 bits (+/-255), the channel LLR is 8 bits (+/-127)
  logic [6:0]  m1 [12][81];
  logic [6:0]  m2 [12][81];
  logic [4:0]  ix [12][81];
  logic [23:0] sg [12][81];

  logic [4:0]  ecnt [12];
  logic [4:0]  ecol [12][24];
  logic [6:0]  esh  [12][24];

  logic [6:0]  lm1 [81];
  logic [6:0]  lm2 [81];
  logic [4:0]  lix [81];
  logic        lsp [81];
  logic [23:0] lns [81];
  logic        par [81];

  logic [3:0]  ly;
  logic [4:0]  e;
  logic [5:0]  it;
  logic        all_ok, changed;
  logic [5:0]  wout;

  wire [4:0]  cur_col = ecol[ly][e];
  wire [6:0]  cur_sh  = esh[ly][e];
  wire [4:0]  d_ly    = ecnt[ly];

  function automatic signed [8:0] sat9(input signed [10:0] v);
    begin
      if (v > 11'sd255) sat9 = 9'sd255;
      else if (v < -11'sd255) sat9 = -9'sd255;
      else sat9 = v[8:0];
    end
  endfunction
  function automatic [6:0] scale7(input [6:0] m);
    begin
      scale7 = 7'(({2'b00, m} + {1'b0, m, 1'b0}) >> 2);      // (3 m) >> 2
    end
  endfunction

  assign s_axis_ready = (state == S_LOAD);
  wire in_xfer = s_axis_valid & s_axis_ready;
  wire in_last = (ncnt == n_tot - 11'd1);

  // output word
  logic [31:0] ow;
  always_comb begin
    ow = 32'd0;
    for (int t = 0; t < 32; t++) begin
      logic [10:0] idx;
      logic [4:0]  blk;
      logic [6:0]  bit_;
      idx = 11'(wout) * 11'd32 + 11'(t);
      if (z_rom == 7'd81) blk = 5'(idx / 11'd81); else blk = 5'(idx / 11'd27);
      bit_ = 7'(idx - 11'(blk) * 11'(z_rom));
      if (idx < k_tot) ow[t] = post[blk][bit_][8];
    end
  end
  assign m_axis_valid = (state == S_OUT);
  assign m_axis_data  = ow;
  assign m_axis_last  = (wout == 6'((k_tot + 11'd31) >> 5) - 6'd1);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state   <= S_LOAD;
      ncnt    <= '0;
      bidx    <= '0;
      blkidx  <= '0;
      built_v <= 1'b0;
      err_len <= 1'b0;
      wout    <= '0;
      m_ok    <= 1'b0;
      m_iters <= '0;
    end else begin
      err_len <= 1'b0;
      case (state)
        S_LOAD: if (in_xfer) begin
          if (ncnt == 11'd0) begin
            code_q  <= code;
            maxit_q <= (max_iter == 6'd0) ? 6'd1 : max_iter;
          end
          post[blkidx][bidx] <= (s_axis_data == -8'sd128) ? -9'sd127 : 9'(s_axis_data);
          if (s_axis_last != in_last) err_len <= 1'b1;
          if (in_last) begin
            ncnt   <= '0;
            bidx   <= '0;
            blkidx <= '0;
            if (built_v && built_code == code_q) state <= S_PRE;
            else begin
              bi <= '0;
              bc <= '0;
              for (int i = 0; i < 12; i++) ecnt[i] <= '0;
              state <= S_BUILD;
            end
          end else begin
            ncnt <= ncnt + 11'd1;
            if (bidx == z_rom - 7'd1) begin
              bidx   <= '0;
              blkidx <= blkidx + 5'd1;
            end else bidx <= bidx + 7'd1;
          end
        end
        S_BUILD: begin
          logic       v;
          logic [6:0] sh;
          logic [5:0] cc;
          v  = 1'b0;
          sh = 7'd0;
          cc = {1'b0, bc} - {1'b0, kb_rom};         // parity column index (valid when bc >= kb)
          if (bc < kb_rom) begin
            v  = rom_valid;
            sh = rom_shift;
          end else if (bc == kb_rom) begin
            if (bi == 4'd0 || bi == mb_rom - 4'd1) begin v = 1'b1; sh = xs_rom; end
            else if (bi == {1'b0, mb_rom[3:1]}) begin v = 1'b1; sh = 7'd0; end
          end else begin
            if (cc - 6'd1 == {2'b00, bi} || cc == {2'b00, bi}) begin v = 1'b1; sh = 7'd0; end
          end
          if (v) begin
            ecol[bi][ecnt[bi]] <= bc;
            esh[bi][ecnt[bi]]  <= sh;
            ecnt[bi]           <= ecnt[bi] + 5'd1;
          end
          if (bc == 5'd23) begin
            bc <= '0;
            if (bi == mb_rom - 4'd1) begin
              built_code <= code_q;
              built_v    <= 1'b1;
              state      <= S_PRE;
            end else bi <= bi + 4'd1;
          end else bc <= bc + 5'd1;
        end
        S_PRE: begin
          for (int i = 0; i < 12; i++)
            for (int r = 0; r < 81; r++) begin
              m1[i][r] <= 7'd0;
              m2[i][r] <= 7'd0;
              ix[i][r] <= 5'd0;
              sg[i][r] <= 24'd0;
            end
          it      <= 6'd1;
          ly      <= 4'd0;
          all_ok  <= 1'b1;
          changed <= 1'b0;
          state   <= S_LINIT;
        end
        S_LINIT: begin
          for (int r = 0; r < 81; r++) begin
            lm1[r] <= 7'd127;
            lm2[r] <= 7'd127;
            lix[r] <= 5'd0;
            lsp[r] <= 1'b0;
            lns[r] <= 24'd0;
            par[r] <= 1'b0;
          end
          e     <= 5'd0;
          state <= S_PA;
        end
        S_PA: begin
          for (int r = 0; r < 81; r++) begin
            if (r < int'(z_rom)) begin
              logic signed [8:0] x, v;
              logic [6:0] om, mag;
              logic signed [10:0] cold;
              logic [8:0] absv;
              logic sgn;
              int idx;
              idx = r + int'(cur_sh);
              if (idx >= int'(z_rom)) idx = idx - int'(z_rom);
              x    = post[cur_col][idx];
              om   = scale7((e == ix[ly][r]) ? m2[ly][r] : m1[ly][r]);
              cold = sg[ly][r][e] ? -11'(signed'({4'b0000, om})) : 11'(signed'({4'b0000, om}));
              v    = sat9(11'(x) - cold);
              sgn  = v[8];
              absv = sgn ? 9'(-v) : 9'(v);
              mag  = (absv > 9'd127) ? 7'd127 : absv[6:0];
              if (mag < lm1[r]) begin
                lm2[r] <= lm1[r];
                lm1[r] <= mag;
                lix[r] <= e;
              end else if (mag < lm2[r]) lm2[r] <= mag;
              lsp[r]    <= lsp[r] ^ sgn;
              lns[r][e] <= sgn;
              par[r]    <= par[r] ^ x[8];
            end
          end
          if (e == d_ly - 5'd1) begin
            e     <= 5'd0;
            state <= S_PB;
          end else e <= e + 5'd1;
        end
        S_PB: begin
          for (int r = 0; r < 81; r++) begin
            if (r < int'(z_rom)) begin
              logic signed [8:0] x, v, xn;
              logic [6:0] om, nm;
              logic signed [10:0] cold, cnew;
              logic ns;
              int idx;
              idx = r + int'(cur_sh);
              if (idx >= int'(z_rom)) idx = idx - int'(z_rom);
              x    = post[cur_col][idx];
              om   = scale7((e == ix[ly][r]) ? m2[ly][r] : m1[ly][r]);
              cold = sg[ly][r][e] ? -11'(signed'({4'b0000, om})) : 11'(signed'({4'b0000, om}));
              v    = sat9(11'(x) - cold);
              nm   = scale7((e == lix[r]) ? lm2[r] : lm1[r]);
              ns   = lsp[r] ^ lns[r][e];
              cnew = ns ? -11'(signed'({4'b0000, nm})) : 11'(signed'({4'b0000, nm}));
              xn   = sat9(11'(v) + cnew);
              post[cur_col][idx] <= xn;
              if (xn[8] != x[8]) changed <= 1'b1;
            end
          end
          if (e == d_ly - 5'd1) state <= S_LEND;
          else e <= e + 5'd1;
        end
        S_LEND: begin
          for (int r = 0; r < 81; r++) begin
            if (r < int'(z_rom)) begin
              m1[ly][r] <= lm1[r];
              m2[ly][r] <= lm2[r];
              ix[ly][r] <= lix[r];
              sg[ly][r] <= lns[r] ^ {24{lsp[r]}};      // sign of each outgoing message
              if (par[r]) all_ok <= 1'b0;
            end
          end
          if (ly == mb_rom - 4'd1) state <= S_IEND;
          else begin
            ly    <= ly + 4'd1;
            state <= S_LINIT;
          end
        end
        S_IEND: begin
          if (all_ok && !changed) begin
            m_ok    <= 1'b1;
            m_iters <= it;
            wout    <= '0;
            state   <= S_OUT;
          end else if (it == maxit_q) begin
            m_ok    <= 1'b0;
            m_iters <= it;
            wout    <= '0;
            state   <= S_OUT;
          end else begin
            it      <= it + 6'd1;
            ly      <= 4'd0;
            all_ok  <= 1'b1;
            changed <= 1'b0;
            state   <= S_LINIT;
          end
        end
        default: begin      // S_OUT
          if (m_axis_valid && m_axis_ready) begin
            if (m_axis_last) begin
              wout  <= '0;
              state <= S_LOAD;
            end else wout <= wout + 6'd1;
          end
        end
      endcase
    end
  end
endmodule
