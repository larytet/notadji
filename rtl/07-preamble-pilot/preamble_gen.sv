// preamble_gen - frequency-domain STF, LTF and pilot-template symbols with tone map (design/07-preamble-pilot.md).
module preamble_gen (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        cmd_valid,
    output logic        cmd_ready,
    input  logic [1:0]  cmd_kind,
    input  logic [3:0]  cmd_log2,
    input  logic        cmd_frame_start,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [33:0] m_axis_data,
    output logic        m_axis_last
);
  // ---------------- tone plan ----------------
  function automatic [9:0] kmin_of(input [3:0] l);
    begin
      case (l)
        4'd6: kmin_of = 10'd1;
        4'd7: kmin_of = 10'd2;
        4'd8: kmin_of = 10'd2;
        default: kmin_of = 10'd3;
      endcase
    end
  endfunction

  function automatic [9:0] kmax_of(input [3:0] l);
    begin
      case (l)
        4'd6: kmax_of = 10'd26;
        4'd7: kmax_of = 10'd58;
        4'd8: kmax_of = 10'd122;
        4'd9: kmax_of = 10'd244;
        default: kmax_of = 10'd500;
      endcase
    end
  endfunction

  // pilot index of |k|: 0 = not a pilot, otherwise 1 + position in the increasing-|k| list
  function automatic [3:0] pilot_pos(input [3:0] l, input [9:0] ak);
    begin
      pilot_pos = 4'd0;
      case (l)
        4'd6: begin
          if (ak == 10'd7)   pilot_pos = 4'd1;
          if (ak == 10'd21)  pilot_pos = 4'd2;
        end
        4'd7: begin
          if (ak == 10'd11)  pilot_pos = 4'd1;
          if (ak == 10'd25)  pilot_pos = 4'd2;
          if (ak == 10'd53)  pilot_pos = 4'd3;
        end
        4'd8: begin
          if (ak == 10'd11)  pilot_pos = 4'd1;
          if (ak == 10'd39)  pilot_pos = 4'd2;
          if (ak == 10'd75)  pilot_pos = 4'd3;
          if (ak == 10'd103) pilot_pos = 4'd4;
        end
        4'd9: begin
          if (ak == 10'd12)  pilot_pos = 4'd1;
          if (ak == 10'd42)  pilot_pos = 4'd2;
          if (ak == 10'd72)  pilot_pos = 4'd3;
          if (ak == 10'd102) pilot_pos = 4'd4;
          if (ak == 10'd132) pilot_pos = 4'd5;
          if (ak == 10'd162) pilot_pos = 4'd6;
          if (ak == 10'd192) pilot_pos = 4'd7;
          if (ak == 10'd222) pilot_pos = 4'd8;
        end
        default: begin
          if (ak == 10'd12)  pilot_pos = 4'd1;
          if (ak == 10'd72)  pilot_pos = 4'd2;
          if (ak == 10'd132) pilot_pos = 4'd3;
          if (ak == 10'd192) pilot_pos = 4'd4;
          if (ak == 10'd252) pilot_pos = 4'd5;
          if (ak == 10'd312) pilot_pos = 4'd6;
          if (ak == 10'd372) pilot_pos = 4'd7;
          if (ak == 10'd432) pilot_pos = 4'd8;
        end
      endcase
    end
  endfunction

  function automatic [3:0] npilot_pos(input [3:0] l);   // pilots per sign
    begin
      case (l)
        4'd6: npilot_pos = 4'd2;
        4'd7: npilot_pos = 4'd3;
        4'd8: npilot_pos = 4'd4;
        default: npilot_pos = 4'd8;
      endcase
    end
  endfunction

  // ---------------- state ----------------
  logic        busy;
  logic [1:0]  kind_q;
  logic [3:0]  log2_q;
  logic [9:0]  b;
  logic [8:0]  pn9;
  logic [6:0]  pol_state;
  logic        pol_q;

  wire [10:0] nn      = 11'd1 << log2_q;
  wire [9:0]  half    = 10'(nn >> 1);
  wire        last_b  = (b == 10'(nn - 11'd1));

  assign cmd_ready    = ~busy | (m_axis_ready & last_b);
  wire   cmd_xfer     = cmd_valid & cmd_ready;
  assign m_axis_valid = busy;
  assign m_axis_last  = last_b;
  wire   out_xfer     = busy & m_axis_ready;

  // subcarrier index
  wire        neg     = (b >= half);
  wire [9:0]  ak      = neg ? (10'(nn) - b) : b;     // |k|; for b = half (k = -N/2) ak = N/2, never used
  wire        used    = (ak >= kmin_of(log2_q)) && (ak <= kmax_of(log2_q));
  wire [3:0]  ppos    = pilot_pos(log2_q, ak);
  wire        is_pil  = used && (ppos != 4'd0);
  wire [3:0]  np      = npilot_pos(log2_q);
  // pilot index j in increasing-k order over all pilots (negative first)
  wire [1:0]  j_neg   = 2'(np - ppos);                    // |k| list position i = ppos-1 -> j = np-1-i = np - ppos
  wire [1:0]  j_pos   = 2'(np + ppos - 4'd1);              // j = np + i (only j mod 4 matters)
  wire [1:0]  jidx    = neg ? j_neg : j_pos;
  wire        pat     = (jidx == 2'd3);
  wire        pil_neg = pol_q ^ pat;                       // 1 = negative sign

  // PN9: x^9 + x^5 + 1
  wire fb1 = pn9[8] ^ pn9[4];
  wire [8:0] pn9_1 = {pn9[7:0], fb1};
  wire fb2 = pn9_1[8] ^ pn9_1[4];
  wire [8:0] pn9_2 = {pn9_1[7:0], fb2};

  wire occ_stf = used && (ak[1:0] == 2'b00);
  wire kind_data = (kind_q[1] == 1'b1);        // kinds 2 and 3
  wire kind_stf  = (kind_q == 2'd0);

  logic [1:0]  ttype;
  logic [15:0] iv, qv;
  logic        pn_use1, pn_use2;

  always_comb begin
    ttype   = 2'd0;
    iv      = 16'd0;
    qv      = 16'd0;
    pn_use1 = 1'b0;
    pn_use2 = 1'b0;
    if (kind_data) begin
      if (is_pil) begin
        ttype = 2'd2;
        iv    = pil_neg ? 16'hF000 : 16'h1000;
      end else if (used) begin
        ttype = 2'd1;
      end
    end else if (kind_stf) begin
      if (occ_stf) begin
        ttype   = 2'd2;
        pn_use2 = 1'b1;
        iv      = fb1 ? 16'd5793 : 16'hE95F;      // +5793 / -5793
        qv      = fb2 ? 16'd5793 : 16'hE95F;
      end
    end else begin
      if (used) begin
        ttype   = 2'd2;
        pn_use1 = 1'b1;
        iv      = fb1 ? 16'h1000 : 16'hF000;
      end
    end
  end

  assign m_axis_data = {ttype, qv, iv};

  // polarity LFSR x^7 + x^4 + 1, seed all ones
  wire [6:0] pol_s  = cmd_frame_start ? 7'h7F : pol_state;
  wire       pol_fb = ^(pol_s & 7'b1001000);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      busy      <= 1'b0;
      b         <= '0;
      pn9       <= 9'h1FF;
      pol_state <= 7'h7F;
      kind_q    <= 2'd0;
      log2_q    <= 4'd6;
      pol_q     <= 1'b0;
    end else begin
      if (out_xfer) begin
        if (pn_use2) pn9 <= pn9_2;
        else if (pn_use1) pn9 <= pn9_1;
        b <= b + 1'b1;
        if (last_b) busy <= 1'b0;
      end
      if (cmd_xfer) begin
        busy   <= 1'b1;
        b      <= '0;
        kind_q <= cmd_kind;
        log2_q <= (cmd_log2 < 4'd6) ? 4'd6 : (cmd_log2 > 4'd10) ? 4'd10 : cmd_log2;
        pn9    <= 9'h1FF;
        if (cmd_kind[1]) begin
          // polarity bit of this data symbol: feedback of the 7-bit LFSR, restarted on frame_start
          pol_q     <= pol_fb;
          pol_state <= {pol_s[5:0], pol_fb};
        end
      end
    end
  end
endmodule
