// ldpc_enc - quasi-cyclic LDPC encoder, block-serial, systematic (design/13-ldpc-encoder.md).
module ldpc_enc (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [2:0]  code,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [31:0] s_axis_data,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic        m_axis_last,
    output logic        err_len
);
  typedef enum logic [2:0] {S_LOAD, S_ACC, S_P0, S_CHAIN, S_OUT} state_t;
  state_t state;

  logic [2:0]    code_q;
  wire           first_word_sel;
  logic [5:0]    wcnt;                  // input word counter (up to 51 words)
  logic [3:0]    ri;                    // accumulate: block row
  logic [4:0]    cj;                    // accumulate: block column
  logic [3:0]    pc;                    // chain step
  logic [5:0]    wout;
  logic [1631:0] msg;
  logic [80:0]   lam[12];
  logic [971:0]  pf;
  logic [80:0]   p0, pcur;

  // ---------------- code parameters ----------------
  logic [2:0]  code_sel;
  logic        r_valid;
  logic [6:0]  r_shift, r_z, r_xs;
  logic [3:0]  r_mb;
  logic [4:0]  r_kb;
  logic [3:0]  rom_row;
  logic [4:0]  rom_col;
  ldpc_code_rom u_rom (.code(code_sel), .row(rom_row), .col(rom_col), .valid(r_valid), .shift(r_shift),
                       .z(r_z), .mb(r_mb), .kb(r_kb), .xs(r_xs));

  assign first_word_sel = (state == S_LOAD) && (wcnt == 6'd0);
  assign code_sel = first_word_sel ? code : code_q;
  assign rom_row  = ri;
  assign rom_col  = cj;

  wire [10:0] k_bits = 11'(r_kb) * 11'(r_z);
  wire [10:0] n_bits = 11'(24) * 11'(r_z);
  wire [5:0]  nin    = 6'((k_bits + 11'd31) >> 5);
  wire [5:0]  nout   = 6'((n_bits + 11'd31) >> 5);

  // ---------------- rotate: out[r] = in[(r + s) mod z] for r < z ----------------
  function automatic [80:0] rot(input [80:0] v, input [6:0] s, input [6:0] z);
    integer r;
    integer idx;
    integer si, zi;
    begin
      rot = 81'd0;
      si  = {25'd0, s};
      zi  = {25'd0, z};
      for (r = 0; r < 81; r = r + 1) begin
        if (r < zi) begin
          idx = r + si;
          if (idx >= zi) idx = idx - zi;
          rot[r] = v[idx];
        end
      end
    end
  endfunction

  // block j of the message (81 bits starting at j*Z; only the low Z bits are used)
  wire [10:0]  blk_pos = 11'(cj) * 11'(r_z);
  wire [80:0]  blk     = msg[blk_pos +: 81];

  // XOR of all lambda rows
  logic [80:0] lam_xor;
  always_comb begin
    lam_xor = 81'd0;
    for (int i = 0; i < 12; i++) if (i < r_mb) lam_xor = lam_xor ^ lam[i];
  end

  // chain value for the current step
  logic [80:0] pn;
  always_comb begin
    if (pc == 4'd0) pn = lam[0] ^ rot(p0, r_xs, r_z);
    else begin
      pn = lam[pc] ^ pcur;
      if (pc == {1'b0, r_mb[3:1]}) pn = pn ^ p0;
    end
  end

  // ---------------- output word ----------------
  logic [31:0] ow;
  always_comb begin
    ow = 32'd0;
    for (int t = 0; t < 32; t++) begin
      logic [10:0] b;
      b = 11'(wout) * 11'd32 + 11'(t);
      if (b < k_bits) ow[t] = msg[b];
      else if (b < n_bits) ow[t] = pf[10'(b - k_bits)];
    end
  end

  assign s_axis_ready = (state == S_LOAD);
  assign m_axis_valid = (state == S_OUT);
  assign m_axis_data  = ow;
  assign m_axis_last  = (wout == nout - 6'd1);

  wire in_xfer  = s_axis_valid & s_axis_ready;
  wire out_xfer = m_axis_valid & m_axis_ready;
  wire in_last  = (wcnt == nin - 6'd1);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state   <= S_LOAD;
      wcnt    <= '0;
      ri      <= '0;
      cj      <= '0;
      pc      <= '0;
      wout    <= '0;
      err_len <= 1'b0;
      code_q  <= '0;
    end else begin
      err_len <= 1'b0;
      case (state)
        S_LOAD: if (in_xfer) begin
          msg[{wcnt, 5'd0} +: 32] <= s_axis_data;
          if (wcnt == 6'd0) code_q <= code;
          if (s_axis_last != in_last) err_len <= 1'b1;
          if (in_last) begin
            wcnt  <= '0;
            ri    <= '0;
            cj    <= '0;
            for (int i = 0; i < 12; i++) lam[i] <= 81'd0;
            state <= S_ACC;
          end else begin
            wcnt <= wcnt + 6'd1;
          end
        end
        S_ACC: begin
          if (r_valid) lam[ri] <= lam[ri] ^ rot(blk, r_shift, r_z);
          if (cj == r_kb - 5'd1) begin
            cj <= '0;
            if (ri == r_mb - 4'd1) begin
              ri    <= '0;
              state <= S_P0;
            end else ri <= ri + 4'd1;
          end else cj <= cj + 5'd1;
        end
        S_P0: begin
          p0   <= lam_xor;
          pcur <= lam_xor;
          pf[80:0] <= lam_xor;
          pc   <= '0;
          state <= S_CHAIN;
        end
        S_CHAIN: begin
          pf[10'(11'(pc + 4'd1) * 11'(r_z)) +: 81] <= pn;
          pcur <= pn;
          if (pc == r_mb - 4'd2) begin
            wout  <= '0;
            state <= S_OUT;
          end else pc <= pc + 4'd1;
        end
        default: begin   // S_OUT
          if (out_xfer) begin
            if (m_axis_last) begin
              wout  <= '0;
              state <= S_LOAD;
            end else wout <= wout + 6'd1;
          end
        end
      endcase
    end
  end

  wire unused_ok = &{1'b0, first_word_sel};
endmodule
