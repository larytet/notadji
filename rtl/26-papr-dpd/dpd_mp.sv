// dpd_mp - memory-polynomial pre-distorter, orders 1, 3, 5, memory 3 (design/26-papr-dpd.md section 1.3).
module dpd_mp #(
    parameter int NCM = 3                       // complex multiply-accumulate units: 1, 3 or 9
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        wr_en,
    input  logic [3:0]  wr_idx,                 // coefficient t = 3 j + m, j the order index, m the delay
    input  logic signed [15:0] wr_re,
    input  logic signed [15:0] wr_im,
    input  logic        commit,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [31:0] s_data,
    output logic        m_valid,
    output logic [31:0] m_data
);
  localparam int G = (9 + NCM - 1) / NCM;
  typedef enum logic [2:0] {S_IDLE, S_B1, S_B2, S_B3, S_MAC, S_OUT} state_t;
  state_t state;
  logic [3:0] grp;

  logic signed [15:0] a_re [9];
  logic signed [15:0] a_im [9];
  logic signed [15:0] w_re [9];
  logic signed [15:0] w_im [9];
  logic               pend;

  logic signed [15:0] xi, xq;
  logic [15:0]        r, r2;
  logic signed [15:0] bi [3][3];
  logic signed [15:0] bq [3][3];

  wire signed [31:0] ii = xi * xi;
  wire signed [31:0] qq = xq * xq;
  wire [31:0] m2 = 32'(ii) + 32'(qq);
  wire [16:0] r_full = m2[31:15];
  wire signed [32:0] pr2 = $signed({1'b0, r}) * $signed({1'b0, r});
  wire signed [15:0] rs  = $signed({1'b0, r[14:0]});
  wire signed [15:0] r2s = $signed({1'b0, r2[14:0]});

  function automatic logic signed [15:0] sat16(input logic signed [47:0] v);
    if (v > 48'sd32767) sat16 = 16'sh7FFF;
    else if (v < -48'sd32768) sat16 = 16'sh8000;
    else sat16 = v[15:0];
  endfunction

  logic signed [41:0] acc_r, acc_i;
  logic signed [41:0] sum_r, sum_i;
  always_comb begin
    sum_r = acc_r;
    sum_i = acc_i;
    for (int l = 0; l < NCM; l++) begin
      int t;
      t = int'(grp) * NCM + l;
      if (t < 9) begin
        sum_r = sum_r + 42'(a_re[t] * bi[t/3][t%3]) - 42'(a_im[t] * bq[t/3][t%3]);
        sum_i = sum_i + 42'(a_re[t] * bq[t/3][t%3]) + 42'(a_im[t] * bi[t/3][t%3]);
      end
    end
  end

  assign s_ready = (state == S_IDLE) && !pend;
  wire unused_ok = &{1'b0, r_full[16], pr2[32:31], pr2[14:0], r[15], r2[15], m2[14:0]};

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state <= S_IDLE;
      grp <= '0;
      pend <= 1'b0;
      m_valid <= 1'b0;
      m_data <= '0;
      acc_r <= '0;
      acc_i <= '0;
      xi <= '0;
      xq <= '0;
      r <= '0;
      r2 <= '0;
      /* verilator lint_off BLKSEQ */
      for (int t = 0; t < 9; t++) begin
        a_re[t] = (t == 0) ? 16'sd4096 : 16'sd0;      // identity until programmed
        a_im[t] = 16'sd0;
        w_re[t] = (t == 0) ? 16'sd4096 : 16'sd0;
        w_im[t] = 16'sd0;
        bi[t/3][t%3] = '0;
        bq[t/3][t%3] = '0;
      end
      /* verilator lint_on BLKSEQ */
    end else begin
      m_valid <= 1'b0;
      if (wr_en && wr_idx < 4'd9) begin
        w_re[wr_idx] <= wr_re;
        w_im[wr_idx] <= wr_im;
      end
      if (commit) pend <= 1'b1;
      case (state)
        S_IDLE: begin
          if (pend) begin
            for (int t = 0; t < 9; t++) begin
              a_re[t] <= w_re[t];
              a_im[t] <= w_im[t];
            end
            pend <= 1'b0;
          end else if (s_valid) begin
            xi <= s_data[15:0];
            xq <= s_data[31:16];
            state <= S_B1;
          end
        end
        S_B1: begin
          r <= (r_full > 17'd32767) ? 16'd32767 : r_full[15:0];
          state <= S_B2;
        end
        S_B2: begin
          r2 <= 16'((pr2 + 33'sd16384) >>> 15);
          state <= S_B3;
        end
        S_B3: begin
          for (int j = 0; j < 3; j++) begin
            bi[j][2] <= bi[j][1];
            bq[j][2] <= bq[j][1];
            bi[j][1] <= bi[j][0];
            bq[j][1] <= bq[j][0];
          end
          bi[0][0] <= xi;
          bq[0][0] <= xq;
          bi[1][0] <= 16'((xi * rs + 32'sd16384) >>> 15);
          bq[1][0] <= 16'((xq * rs + 32'sd16384) >>> 15);
          bi[2][0] <= 16'((xi * r2s + 32'sd16384) >>> 15);
          bq[2][0] <= 16'((xq * r2s + 32'sd16384) >>> 15);
          grp <= '0;
          acc_r <= '0;
          acc_i <= '0;
          state <= S_MAC;
        end
        S_MAC: begin
          acc_r <= sum_r;
          acc_i <= sum_i;
          if (int'(grp) == G - 1) state <= S_OUT;
          grp <= grp + 4'd1;
        end
        default: begin
          m_valid <= 1'b1;
          m_data  <= {sat16((48'(acc_i) + 48'sd2048) >>> 12), sat16((48'(acc_r) + 48'sd2048) >>> 12)};
          state   <= S_IDLE;
        end
      endcase
    end
  end
endmodule
