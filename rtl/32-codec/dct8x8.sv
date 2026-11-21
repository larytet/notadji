// Module 32: 8 x 8 integer DCT / inverse (the transform of profile SL2). Bit-exact with sl2_fwd / sl2_inv of fw/32-codec/sl2.c.
// 64 samples in (raster order, one per clock), the first transform stage (columns) after the last one, the second stage
// (rows) streams the 64 results out in raster order. 192 clocks per block (no overlap of blocks), 8 multipliers.
module dct8x8 (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        inverse,           // sampled with the first sample of a block
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic signed [15:0] s_axis_data,    // forward: residual (9 bit used), inverse: coefficient
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic signed [15:0] m_axis_data,
    output logic        m_axis_last,
    output logic        err_len
);
  function automatic signed [7:0] tc(input [2:0] a, input [2:0] b);
    case ({a, b})
      6'o00, 6'o01, 6'o02, 6'o03, 6'o04, 6'o05, 6'o06, 6'o07: tc = 8'sd64;
      6'o10: tc = 8'sd89;  6'o11: tc = 8'sd75;  6'o12: tc = 8'sd50;  6'o13: tc = 8'sd18;
      6'o14: tc = -8'sd18; 6'o15: tc = -8'sd50; 6'o16: tc = -8'sd75; 6'o17: tc = -8'sd89;
      6'o20: tc = 8'sd83;  6'o21: tc = 8'sd36;  6'o22: tc = -8'sd36; 6'o23: tc = -8'sd83;
      6'o24: tc = -8'sd83; 6'o25: tc = -8'sd36; 6'o26: tc = 8'sd36;  6'o27: tc = 8'sd83;
      6'o30: tc = 8'sd75;  6'o31: tc = -8'sd18; 6'o32: tc = -8'sd89; 6'o33: tc = -8'sd50;
      6'o34: tc = 8'sd50;  6'o35: tc = 8'sd89;  6'o36: tc = 8'sd18;  6'o37: tc = -8'sd75;
      6'o40: tc = 8'sd64;  6'o41: tc = -8'sd64; 6'o42: tc = -8'sd64; 6'o43: tc = 8'sd64;
      6'o44: tc = 8'sd64;  6'o45: tc = -8'sd64; 6'o46: tc = -8'sd64; 6'o47: tc = 8'sd64;
      6'o50: tc = 8'sd50;  6'o51: tc = -8'sd89; 6'o52: tc = 8'sd18;  6'o53: tc = 8'sd75;
      6'o54: tc = -8'sd75; 6'o55: tc = -8'sd18; 6'o56: tc = 8'sd89;  6'o57: tc = -8'sd50;
      6'o60: tc = 8'sd36;  6'o61: tc = -8'sd83; 6'o62: tc = 8'sd83;  6'o63: tc = -8'sd36;
      6'o64: tc = -8'sd36; 6'o65: tc = 8'sd83;  6'o66: tc = -8'sd83; 6'o67: tc = 8'sd36;
      6'o70: tc = 8'sd18;  6'o71: tc = -8'sd50; 6'o72: tc = 8'sd75;  6'o73: tc = -8'sd89;
      6'o74: tc = 8'sd89;  6'o75: tc = -8'sd75; 6'o76: tc = 8'sd50;  6'o77: tc = -8'sd18;
      default: tc = 8'sd0;
    endcase
  endfunction
  function automatic signed [15:0] sat16(input signed [39:0] v);
    if (v > 40'sd32767) sat16 = 16'sd32767;
    else if (v < -40'sd32768) sat16 = -16'sd32768;
    else sat16 = v[15:0];
  endfunction

  typedef enum logic [1:0] {S_LOAD, S_S1, S_S2} state_t;
  state_t state;
  logic signed [15:0] xm [64];
  logic signed [31:0] ym [64];
  logic [6:0] cnt;
  logic       inv_q;
  wire        first = (state == S_LOAD) && (cnt == 7'd0);
  assign s_axis_ready = (state == S_LOAD);
  wire in_xfer = s_axis_valid & s_axis_ready;

  // stage 1: Y[i][j] = (sum_k A[i][k] X[k][j] + r1) >> s1   (A = T forward, T^T inverse)
  wire [2:0] i1 = cnt[5:3], j1 = cnt[2:0];
  logic signed [39:0] acc1, acc2;
  always_comb begin
    acc1 = 40'sd0;
    for (int k = 0; k < 8; k++)
      acc1 = acc1 + 40'(xm[k * 8 + int'(j1)]) * 40'((inv_q ? tc(3'(k), i1) : tc(i1, 3'(k))));
    acc2 = 40'sd0;
    for (int k = 0; k < 8; k++)
      acc2 = acc2 + 40'(ym[int'(i1) * 8 + k]) * 40'((inv_q ? tc(3'(k), j1) : tc(j1, 3'(k))));
  end
  wire signed [39:0] y1 = inv_q ? ((acc1 + 40'sd64) >>> 7) : ((acc1 + 40'sd2) >>> 2);
  wire signed [39:0] o2 = inv_q ? ((acc2 + 40'sd2048) >>> 12) : ((acc2 + 40'sd256) >>> 9);

  assign m_axis_valid = (state == S_S2);
  assign m_axis_data  = sat16(o2);
  assign m_axis_last  = (state == S_S2) && (cnt == 7'd63);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state <= S_LOAD;
      cnt <= '0;
      inv_q <= 1'b0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      case (state)
        S_LOAD: if (in_xfer) begin
          if (first) inv_q <= inverse;
          xm[cnt[5:0]] <= s_axis_data;
          if (s_axis_last != (cnt == 7'd63)) err_len <= 1'b1;
          if (cnt == 7'd63) begin
            cnt <= '0;
            state <= S_S1;
          end else cnt <= cnt + 7'd1;
        end
        S_S1: begin
          ym[cnt[5:0]] <= 32'(y1);
          if (cnt == 7'd63) begin
            cnt <= '0;
            state <= S_S2;
          end else cnt <= cnt + 7'd1;
        end
        default: if (m_axis_ready) begin
          if (cnt == 7'd63) begin
            cnt <= '0;
            state <= S_LOAD;
          end else cnt <= cnt + 7'd1;
        end
      endcase
    end
  end
  wire unused_ok = &{1'b0, y1[39:32]};
endmodule
