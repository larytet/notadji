// Module 30: chase combiner for retransmitted codewords (PHY-017). See design/30-soft-combining.md.
// LLR stream in (8-bit signed, one per beat), combined LLR stream out (2 clocks latency).
module llr_combiner #(
    parameter int DEPTH = 8,
    parameter int NMAX  = 1944,
    parameter int PEND  = 8
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        mode,                   // 0 bypass, 1 combine
    input  logic [2:0]  code,                   // sampled with the first LLR of a codeword (as the key)
    input  logic [15:0] key_seq,
    input  logic [7:0]  key_cw,
    input  logic [5:0]  maxit,                  // sideband passed to m_maxit (decoder iteration limit)
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic signed [7:0] s_axis_data,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic signed [7:0] m_axis_data,
    output logic        m_axis_last,
    output logic [2:0]  m_code,                 // sideband of the codeword at the output
    output logic [5:0]  m_maxit,
    input  logic        res_valid,              // decoder result of the oldest pending codeword
    input  logic        res_ok,
    input  logic        drop_seq_valid,
    input  logic [15:0] drop_seq,
    input  logic        drop_all,
    output logic [15:0] n_hit,
    output logic [15:0] n_miss,
    output logic [15:0] n_evict,
    output logic [15:0] n_ovf,
    output logic [$clog2(DEPTH+1)-1:0] occupancy
);
  localparam int SW = (DEPTH > 1) ? $clog2(DEPTH) : 1;
  localparam int PW = (PEND > 1) ? $clog2(PEND) : 1;
  localparam int AW = $clog2(DEPTH * NMAX);
  localparam int IW = $clog2(NMAX);

  // ---------------- slot state ----------------
  logic              valid_q [DEPTH];
  logic [15:0]       seq_q   [DEPTH];
  logic [7:0]        cw_q    [DEPTH];
  logic [2:0]        cd_q    [DEPTH];
  logic [15:0]       stamp_q [DEPTH];
  logic [15:0]       alloc_q;
  logic signed [7:0] mem [DEPTH * NMAX];

  // ---------------- pending results ----------------
  logic              pu_q [PEND];
  logic [SW-1:0]     ps_q [PEND];
  logic [15:0]       pq_q [PEND];
  logic [7:0]        pc_q [PEND];
  logic [2:0]        pd_q [PEND];
  logic [PW-1:0]     prd_q, pwr_q;
  logic [$clog2(PEND+1)-1:0] pcnt_q;

  // ---------------- input side ----------------
  logic              in_first;                 // next accepted LLR is the first of a codeword
  logic [IW-1:0]     idx_q;
  logic [SW-1:0]     cur_slot;
  logic              cur_hit, cur_use;
  logic [2:0]        cur_code;
  logic [5:0]        cur_maxit;

  wire pend_full = (pcnt_q == PEND[$clog2(PEND+1)-1:0]);
  logic adv;
  assign adv = ~m_axis_valid | m_axis_ready;
  assign s_axis_ready = adv & ~(in_first & pend_full);
  wire in_xfer  = s_axis_valid & s_axis_ready;
  wire do_first = in_xfer & in_first;

  // lookup, free slot, victim
  logic          found, free_found;
  logic [SW-1:0] hit_slot, free_slot, vic_slot, slot_sel;
  logic [15:0]   maxage, age;
  always_comb begin
    found = 1'b0;
    hit_slot = '0;
    free_found = 1'b0;
    free_slot = '0;
    vic_slot = '0;
    maxage = 16'd0;
    for (int i = DEPTH - 1; i >= 0; i--) begin
      if (valid_q[i] && seq_q[i] == key_seq && cw_q[i] == key_cw && cd_q[i] == code) begin
        found = 1'b1;
        hit_slot = SW'(i);
      end
      if (!valid_q[i]) begin
        free_found = 1'b1;
        free_slot = SW'(i);
      end
    end
    for (int i = 0; i < DEPTH; i++) begin
      age = alloc_q - stamp_q[i];
      if (i == 0 || age > maxage) begin
        maxage = age;
        vic_slot = SW'(i);
      end
    end
    slot_sel = found ? hit_slot : (free_found ? free_slot : vic_slot);
  end

  // next state of the slots: first-LLR allocation, then result, then drop
  logic              v_nx [DEPTH];
  logic [15:0]       sq_nx [DEPTH];
  logic [7:0]        cw_nx [DEPTH];
  logic [2:0]        cd_nx [DEPTH];
  logic [15:0]       st_nx [DEPTH];
  logic [15:0]       alloc_nx;
  logic              v1 [DEPTH];
  logic [SW-1:0]     ps;
  always_comb begin
    for (int i = 0; i < DEPTH; i++) begin
      v1[i] = valid_q[i];
      sq_nx[i] = seq_q[i];
      cw_nx[i] = cw_q[i];
      cd_nx[i] = cd_q[i];
      st_nx[i] = stamp_q[i];
    end
    alloc_nx = alloc_q;
    ps = '0;
    if (do_first && mode && !found) begin
      v1[slot_sel] = 1'b1;
      sq_nx[slot_sel] = key_seq;
      cw_nx[slot_sel] = key_cw;
      cd_nx[slot_sel] = code;
      st_nx[slot_sel] = alloc_q;
      alloc_nx = alloc_q + 16'd1;
    end
    for (int i = 0; i < DEPTH; i++) v_nx[i] = v1[i];
    if (res_valid && pcnt_q != 0 && pu_q[prd_q]) begin
      ps = ps_q[prd_q];
      if (res_ok && v1[ps] && sq_nx[ps] == pq_q[prd_q] && cw_nx[ps] == pc_q[prd_q] && cd_nx[ps] == pd_q[prd_q])
        v_nx[ps] = 1'b0;
    end
    if (drop_all) begin
      for (int i = 0; i < DEPTH; i++) v_nx[i] = 1'b0;
    end else if (drop_seq_valid) begin
      for (int i = 0; i < DEPTH; i++) if (sq_nx[i] == drop_seq) v_nx[i] = 1'b0;
    end
  end

  // address and flags of the beat entering stage A
  wire [SW-1:0] beat_slot = in_first ? slot_sel : cur_slot;
  wire          beat_hit  = in_first ? (found & mode) : cur_hit;
  wire          beat_use  = in_first ? mode : cur_use;
  wire [2:0]    beat_code = in_first ? code : cur_code;
  wire [5:0]    beat_mi   = in_first ? maxit : cur_maxit;
  wire [AW-1:0] beat_addr = AW'(beat_slot) * AW'(NMAX) + AW'(idx_q);

  // stage A
  logic              a_v, a_last, a_hit, a_use;
  logic signed [7:0] a_data;
  logic [AW-1:0]     a_addr;
  logic [2:0]        a_code;
  logic [5:0]        a_mi;
  logic signed [7:0] rdata;

  function automatic logic signed [7:0] sat127(input logic signed [8:0] v);
    if (v > 9'sd127) sat127 = 8'sd127;
    else if (v < -9'sd127) sat127 = -8'sd127;
    else sat127 = v[7:0];
  endfunction

  wire signed [7:0] a_data_c = (a_data < -8'sd127) ? -8'sd127 : a_data;   // -128 is outside the LLR range
  wire signed [7:0] comb_v = a_hit ? sat127(9'(a_data_c) + 9'(rdata)) : a_data_c;

  integer k;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      for (k = 0; k < DEPTH; k++) begin
        valid_q[k] <= 1'b0;
        seq_q[k] <= '0;
        cw_q[k] <= '0;
        cd_q[k] <= '0;
        stamp_q[k] <= '0;
      end
      alloc_q <= '0;
      prd_q <= '0;
      pwr_q <= '0;
      pcnt_q <= '0;
      in_first <= 1'b1;
      idx_q <= '0;
      cur_slot <= '0;
      cur_hit <= 1'b0;
      cur_use <= 1'b0;
      cur_code <= '0;
      cur_maxit <= '0;
      a_v <= 1'b0;
      a_last <= 1'b0;
      a_hit <= 1'b0;
      a_use <= 1'b0;
      a_data <= '0;
      a_addr <= '0;
      a_code <= '0;
      a_mi <= '0;
      m_axis_valid <= 1'b0;
      m_axis_data <= '0;
      m_axis_last <= 1'b0;
      m_code <= '0;
      m_maxit <= '0;
      n_hit <= '0;
      n_miss <= '0;
      n_evict <= '0;
      n_ovf <= '0;
    end else begin
      for (k = 0; k < DEPTH; k++) begin
        valid_q[k] <= v_nx[k];
        seq_q[k] <= sq_nx[k];
        cw_q[k] <= cw_nx[k];
        cd_q[k] <= cd_nx[k];
        stamp_q[k] <= st_nx[k];
      end
      alloc_q <= alloc_nx;
      // pending FIFO
      if (res_valid && pcnt_q != 0) prd_q <= (prd_q == PW'(PEND - 1)) ? '0 : prd_q + PW'(1);
      if (do_first) begin
        pu_q[pwr_q] <= mode;
        ps_q[pwr_q] <= slot_sel;
        pq_q[pwr_q] <= key_seq;
        pc_q[pwr_q] <= key_cw;
        pd_q[pwr_q] <= code;
        pwr_q <= (pwr_q == PW'(PEND - 1)) ? '0 : pwr_q + PW'(1);
      end
      pcnt_q <= pcnt_q + (do_first ? 1 : 0) - ((res_valid && pcnt_q != 0) ? 1 : 0);
      // counters
      if (do_first && mode) begin
        if (found) n_hit <= n_hit + 16'd1;
        else begin
          n_miss <= n_miss + 16'd1;
          if (!free_found) n_evict <= n_evict + 16'd1;
        end
      end
      if (s_axis_valid && adv && in_first && pend_full) n_ovf <= n_ovf + 16'd1;
      // input bookkeeping
      if (in_xfer) begin
        if (in_first) begin
          cur_slot <= slot_sel;
          cur_hit <= found & mode;
          cur_use <= mode;
          cur_code <= code;
          cur_maxit <= maxit;
        end
        if (s_axis_last) begin
          in_first <= 1'b1;
          idx_q <= '0;
        end else begin
          in_first <= 1'b0;
          idx_q <= idx_q + IW'(1);
        end
      end
      // pipeline
      if (adv) begin
        m_axis_valid <= a_v;
        m_axis_data <= comb_v;
        m_axis_last <= a_last;
        m_code <= a_code;
        m_maxit <= a_mi;
        if (a_v && a_use) mem[a_addr] <= comb_v;
        a_v <= in_xfer;
        a_data <= s_axis_data;
        a_last <= s_axis_last;
        a_hit <= beat_hit;
        a_use <= beat_use;
        a_addr <= beat_addr;
        a_code <= beat_code;
        a_mi <= beat_mi;
      end
    end
  end

  // registered read, enabled together with the pipeline
  always_ff @(posedge clk) if (adv) rdata <= mem[beat_addr];

  always_comb begin
    occupancy = '0;
    for (int i = 0; i < DEPTH; i++) occupancy = occupancy + ($bits(occupancy))'(valid_q[i]);
  end
endmodule
