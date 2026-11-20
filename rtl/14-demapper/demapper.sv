// demapper - folded max-log soft demapper, 8-bit LLRs, positive = bit 0 (design/14-demapper.md).
module demapper (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [2:0]  mod,
    input  logic [3:0]  llr_shift,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [31:0] s_axis_data,       // {Q, I}
    input  logic [7:0]  s_csi,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [63:0] m_axis_data,       // eight 8-bit LLRs, LLR k in bits 8k+7..8k
    output logic [3:0]  m_nbits,
    input  logic        s_axis_last,
    output logic        m_axis_last
);
  // thresholds round(2^(m-1) x unit), round(2^(m-2) x unit), round(2^(m-3) x unit) for m = 2, 3, 4
  function automatic [15:0] thr1(input [2:0] m);
    begin
      case (m)
        3'd2: thr1 = 16'd2591;
        3'd3: thr1 = 16'd2528;
        default: thr1 = 16'd2513;
      endcase
    end
  endfunction
  function automatic [15:0] thr2(input [2:0] m);
    begin
      case (m)
        3'd3: thr2 = 16'd1264;
        default: thr2 = 16'd1257;
      endcase
    end
  endfunction

  // folded values of one axis: returns {f3, f2, f1, f0}, 18 bits each
  function automatic [71:0] fold(input [2:0] m, input signed [15:0] a);
    reg signed [17:0] f0, f1, f2, f3, t, aa;
    begin
      f0 = -{{2{a[15]}}, a};
      aa = a[15] ? -{{2{a[15]}}, a} : {{2{a[15]}}, a};
      f1 = 18'sd0; f2 = 18'sd0; f3 = 18'sd0;
      if (m >= 3'd2) f1 = aa - $signed({2'b00, thr1(m)});
      if (m >= 3'd3) begin
        t  = f1[17] ? -f1 : f1;
        f2 = t - $signed({2'b00, thr2(m)});
      end
      if (m >= 3'd4) begin
        t  = f2[17] ? -f2 : f2;
        f3 = t - 18'sd628;
      end
      fold = {f3, f2, f1, f0};
    end
  endfunction

  function automatic [7:0] scale8(input signed [17:0] f, input [7:0] csi, input [3:0] sh);
    reg signed [27:0] p;
    reg signed [27:0] r;
    begin
      p = f * $signed({1'b0, csi});
      if (sh == 4'd0) r = p;
      else r = (p + (28'sd1 <<< (sh - 4'd1))) >>> sh;
      if (r > 28'sd127) scale8 = 8'd127;
      else if (r < -28'sd127) scale8 = 8'h81;      // -127
      else scale8 = r[7:0];
    end
  endfunction

  logic [2:0]  m;
  logic        bpsk;
  logic [3:0]  nb;
  logic [71:0] fi, fq;
  logic [63:0] llrs;

  always_comb begin
    bpsk = 1'b0;
    case (mod)
      3'd1:    m = 3'd1;
      3'd2:    m = 3'd2;
      3'd3:    m = 3'd3;
      3'd4:    m = 3'd4;
      default: begin m = 3'd1; bpsk = 1'b1; end
    endcase
    nb  = bpsk ? 4'd1 : {m, 1'b0} ;
    fi  = fold(m, s_axis_data[15:0]);
    fq  = fold(m, s_axis_data[31:16]);
    llrs = 64'd0;
    if (bpsk) begin
      llrs[7:0] = scale8(fi[17:0], s_csi, llr_shift);
    end else begin
      for (int k = 0; k < 4; k++) begin
        if (k < int'(m)) begin
          llrs[8*k +: 8]       = scale8(fi[18*k +: 18], s_csi, llr_shift);
          llrs[8*(int'(m) + k) +: 8] = scale8(fq[18*k +: 18], s_csi, llr_shift);
        end
      end
    end
  end

  assign s_axis_ready = ~m_axis_valid | m_axis_ready;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      m_axis_valid <= 1'b0;
    end else if (s_axis_ready) begin
      m_axis_valid <= s_axis_valid;
      m_axis_data  <= llrs;
      m_nbits      <= nb;
      m_axis_last  <= s_axis_last;
    end
  end
endmodule
