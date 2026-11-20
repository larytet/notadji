// aead - ChaCha20-Poly1305 frame encrypt / decrypt (RFC 8439), byte streams (design/15-aead.md).
module aead (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [255:0] key,
    input  logic [95:0]  nonce,
    input  logic [7:0]   aad_len,
    input  logic         decrypt,
    input  logic         s_axis_valid,
    output logic         s_axis_ready,
    input  logic [7:0]   s_axis_data,
    input  logic         s_axis_last,
    output logic         m_axis_valid,
    input  logic         m_axis_ready,
    output logic [7:0]   m_axis_data,
    output logic         m_axis_last,
    output logic         st_valid,
    output logic         st_ok,
    output logic         st_short
);
  // ---------------- front end: tail hold for decrypt ----------------
  logic         c_valid, c_ready, c_last, c_empty, c_short;
  logic [7:0]   c_data;
  logic [127:0] c_tail;
  logic         th_ready, th_v, th_last;
  logic [7:0]   th_d;

  tail_hold u_th (
      .clk(clk), .rst_n(rst_n),
      .s_axis_valid(s_axis_valid & decrypt), .s_axis_ready(th_ready), .s_axis_data(s_axis_data), .s_axis_last(s_axis_last),
      .m_axis_valid(th_v), .m_axis_ready(c_ready & decrypt), .m_axis_data(th_d), .m_axis_last(th_last),
      .m_tail(c_tail), .m_empty(c_empty), .m_short(c_short));

  assign c_valid      = decrypt ? th_v : s_axis_valid;
  assign c_data       = decrypt ? th_d : s_axis_data;
  assign c_last       = decrypt ? th_last : s_axis_last;
  assign s_axis_ready = decrypt ? th_ready : c_ready;

  // ---------------- engines ----------------
  typedef enum logic [3:0] {IDLE, PKEY, RUN, FL_AAD, FLUSH_END, LENB, WAITP, FIN, TAGOUT, STAT} state_t;
  state_t state;

  logic [255:0] key_q;
  logic [95:0]  nonce_q;
  logic [7:0]   aad_q;
  logic         dec_q;
  logic         empty_q;
  logic         bad_q;             // decrypt frame shorter than aad_len + 16 bytes
  logic         emp_pend, short_pend;   // one-clock events of tail_hold, kept until the controller is idle
  logic [127:0] emp_tail;

  logic         ch_start, ch_busy, ch_done;
  logic [31:0]  ch_counter;
  logic [511:0] ch_ks;
  logic [31:0]  ctr;
  chacha_block u_ch (.clk(clk), .rst_n(rst_n), .start(ch_start), .key((state == IDLE) ? key : key_q),
                     .nonce((state == IDLE) ? nonce : nonce_q), .counter(ch_counter), .busy(ch_busy), .done(ch_done), .ks(ch_ks));

  logic         p_init, p_blk, p_ready, p_fin, p_tagv;
  logic [127:0] p_r, p_s, p_tag, mblk;
  poly1305 u_poly (.clk(clk), .rst_n(rst_n), .init(p_init), .r_in(p_r), .s_in(p_s), .blk_valid(p_blk), .blk(mblk),
                   .ready(p_ready), .fin(p_fin), .tag_valid(p_tagv), .tag(p_tag));

  // ---------------- datapath state ----------------
  logic [511:0] ks;
  logic         ks_ok;
  logic [511:0] kn;
  logic         kn_valid;
  logic [15:0]  n;                  // bytes accepted
  logic [15:0]  aad_n, ct_n;
  logic [4:0]   mcnt;
  logic         blk_full;
  logic [127:0] tail_q, tag_q;
  logic [4:0]   tcnt;
  logic         o_v, o_l;
  logic [7:0]   o_d;

  assign m_axis_valid = o_v;
  assign m_axis_data  = o_d;
  assign m_axis_last  = o_l;
  wire o_free = ~o_v | m_axis_ready;

  wire        in_aad   = (n < {8'd0, aad_q});
  wire [5:0]  kp       = 6'(n - {8'd0, aad_q});     // payload byte index modulo 64
  wire [7:0]  ksb      = ks[8*kp +: 8];
  wire        byte_ok  = c_valid & o_free & ~blk_full & (in_aad | ks_ok) & (state == RUN);
  assign c_ready       = byte_ok;
  wire        xfer     = c_valid & c_ready;

  wire [7:0]  out_byte = in_aad ? c_data : (c_data ^ ksb);
  wire [7:0]  ct_byte  = (in_aad | dec_q) ? c_data : out_byte;

  assign p_blk = blk_full & p_ready;

  // chacha prefetch and block 0 control
  // not in the clock of ch_done: kn_valid is set one clock later, and a second start would overwrite an unused block
  wire prefetch_go = ~ch_busy & ~ch_done & ~kn_valid & ((state == RUN) | (state == FL_AAD));
  always_comb begin
    ch_start   = 1'b0;
    ch_counter = ctr;
    if (state == IDLE) begin
      ch_start   = ~ch_busy & (c_valid | emp_pend);
      ch_counter = 32'd0;
    end else if (prefetch_go) begin
      ch_start = 1'b1;
    end
  end

  // poly key from block 0
  assign p_init = (state == PKEY) & ch_done;
  assign p_r    = ch_ks[127:0] & 128'h0ffffffc0ffffffc0ffffffc0fffffff;
  assign p_s    = ch_ks[255:128];
  assign p_fin  = (state == WAITP) & ~blk_full & p_ready;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state    <= IDLE;
      st_valid <= 1'b0;
      st_ok    <= 1'b0;
      st_short <= 1'b0;
      o_v      <= 1'b0;
      o_l      <= 1'b0;
      blk_full <= 1'b0;
      mcnt     <= '0;
      mblk     <= '0;
      kn_valid <= 1'b0;
      ks_ok    <= 1'b0;
      n        <= '0;
      aad_n    <= '0;
      ct_n     <= '0;
      ctr      <= '0;
      empty_q  <= 1'b0;
      bad_q    <= 1'b0;
      emp_pend <= 1'b0;
      short_pend <= 1'b0;
    end else begin
      st_valid <= 1'b0;
      st_short <= 1'b0;
      if (c_empty) begin emp_pend <= 1'b1; emp_tail <= c_tail; end
      if (c_short) short_pend <= 1'b1;
      if (o_v && m_axis_ready) o_v <= 1'b0;

      // submit a completed MAC block to the Poly1305 engine
      if (p_blk) begin
        blk_full <= 1'b0;
        mblk     <= '0;
      end

      // keystream prefetch result
      if (ch_done && state != PKEY && state != IDLE) begin
        kn       <= ch_ks;
        kn_valid <= 1'b1;
      end
      if (ch_start) ctr <= (state == IDLE) ? 32'd1 : ctr + 32'd1;

      case (state)
        IDLE: begin
          if (short_pend) begin
            short_pend <= 1'b0;
            st_valid <= 1'b1;
            st_ok    <= 1'b0;
            st_short <= 1'b1;
          end else if (ch_start) begin
            key_q    <= key;
            nonce_q  <= nonce;
            aad_q    <= aad_len;
            dec_q    <= decrypt;
            empty_q  <= emp_pend;
            bad_q    <= emp_pend & (aad_len != 8'd0) & decrypt;
            tail_q   <= emp_tail;
            emp_pend <= 1'b0;
            n        <= '0;
            aad_n    <= '0;
            ct_n     <= '0;
            mcnt     <= '0;
            blk_full <= 1'b0;
            mblk     <= '0;
            kn_valid <= 1'b0;
            ks_ok    <= 1'b0;
            state    <= PKEY;
          end
        end
        PKEY: if (ch_done) state <= empty_q ? FLUSH_END : RUN;
        RUN: begin
          if (!in_aad && !ks_ok && kn_valid) begin
            ks       <= kn;
            ks_ok    <= 1'b1;
            kn_valid <= 1'b0;
          end
          if (xfer) begin
            o_v <= 1'b1;
            o_d <= out_byte;
            o_l <= dec_q & c_last;
            n   <= n + 16'd1;
            if (in_aad) aad_n <= aad_n + 16'd1;
            else begin
              ct_n <= ct_n + 16'd1;
              if (kp == 6'd63) ks_ok <= 1'b0;
            end
            mblk[8*mcnt[3:0] +: 8] <= ct_byte;
            if (mcnt == 5'd15) begin
              blk_full <= 1'b1;
              mcnt     <= '0;
            end else mcnt <= mcnt + 5'd1;
            if (c_last) begin
              if (dec_q) tail_q <= c_tail;
              if (dec_q && in_aad && (n + 16'd1 < {8'd0, aad_q})) bad_q <= 1'b1;
              state <= FLUSH_END;
            end else if (in_aad && (n + 16'd1 == {8'd0, aad_q})) state <= FL_AAD;
          end
        end
        FL_AAD: if (!blk_full) begin
          if (mcnt != 5'd0) begin
            blk_full <= 1'b1;
            mcnt     <= '0;
          end
          state <= RUN;
        end
        FLUSH_END: if (!blk_full) begin
          if (mcnt != 5'd0) begin
            blk_full <= 1'b1;
            mcnt     <= '0;
          end
          state <= LENB;
        end
        LENB: if (!blk_full) begin
          mblk     <= {48'd0, ct_n, 48'd0, aad_n};
          blk_full <= 1'b1;
          state    <= WAITP;
        end
        WAITP: if (!blk_full && p_ready) state <= FIN;
        FIN: if (p_tagv) begin
          tag_q <= p_tag;
          tcnt  <= '0;
          state <= dec_q ? STAT : TAGOUT;
        end
        TAGOUT: if (o_free) begin
          o_v   <= 1'b1;
          o_d   <= tag_q[8*tcnt[3:0] +: 8];
          o_l   <= (tcnt == 5'd15);
          tcnt  <= tcnt + 5'd1;
          if (tcnt == 5'd15) state <= STAT;
        end
        default: begin     // STAT
          st_valid <= 1'b1;
          st_ok    <= dec_q ? ((tag_q == tail_q) && !bad_q) : 1'b1;
          st_short <= dec_q & bad_q;
          state    <= IDLE;
        end
      endcase
    end
  end

  wire unused_ok = &{1'b0, ch_busy};
endmodule
