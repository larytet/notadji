// wht8x8 - 8 x 8 Walsh-Hadamard transform of one block, forward or inverse (design/29-custom-codec.md section 2).
// Forward: R = H X H (residual in, coefficients out). Inverse: X = (H C H + 32) >> 6. H is the sequency-ordered Hadamard matrix.
module wht8x8 (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        inverse,                // sampled with the first input sample of a block
    input  logic        s_valid,
    output logic        s_ready,                // high while a block is being collected
    input  logic signed [15:0] s_data,          // raster order, 64 per block
    output logic        m_valid,
    output logic signed [15:0] m_data,          // raster order, 64 per block
    output logic        m_last
);
  // H[i][j] = +1 where bit (63 - 8 i - j) of the constant is 1
  localparam logic [63:0] HS = 64'b1111111111110000110000111100110010011001100101101010010110101010;
  function automatic logic signed [31:0] hmul(input int i, input int j, input logic signed [31:0] v);
    hmul = HS[63 - 8*i - j] ? v : -v;
  endfunction

  logic signed [31:0] buf0 [64];
  logic [6:0] cnt;
  logic inv_l;
  typedef enum logic [1:0] {S_IN, S_ROW, S_COL, S_OUT} state_t;
  state_t state;

  assign s_ready = (state == S_IN);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state <= S_IN;
      cnt <= '0;
      inv_l <= 1'b0;
      m_valid <= 1'b0;
      m_data <= '0;
      m_last <= 1'b0;
      /* verilator lint_off BLKSEQ */
      for (int k = 0; k < 64; k++) buf0[k] = '0;
      /* verilator lint_on BLKSEQ */
    end else begin
      m_valid <= 1'b0;
      m_last <= 1'b0;
      case (state)
        S_IN: begin
          if (s_valid) begin
            buf0[cnt[5:0]] <= 32'(s_data);
            if (cnt == 7'd0) inv_l <= inverse;
            if (cnt == 7'd63) begin
              cnt <= '0;
              state <= S_ROW;
            end else cnt <= cnt + 7'd1;
          end
        end
        S_ROW: begin
          // every row times H (the matrix is symmetric)
          for (int r = 0; r < 8; r++) begin
            for (int j = 0; j < 8; j++) begin
              logic signed [31:0] a;
              a = 32'sd0;
              for (int k = 0; k < 8; k++) a = a + hmul(j, k, buf0[8*r + k]);
              buf0[8*r + j] <= a;
            end
          end
          state <= S_COL;
        end
        S_COL: begin
          for (int c = 0; c < 8; c++) begin
            for (int i = 0; i < 8; i++) begin
              logic signed [31:0] a;
              a = 32'sd0;
              for (int k = 0; k < 8; k++) a = a + hmul(i, k, buf0[8*k + c]);
              buf0[8*i + c] <= a;
            end
          end
          cnt <= '0;
          state <= S_OUT;
        end
        default: begin
          m_valid <= 1'b1;
          m_data <= inv_l ? 16'((buf0[cnt[5:0]] + 32'sd32) >>> 6) : 16'(buf0[cnt[5:0]]);
          m_last <= (cnt == 7'd63);
          if (cnt == 7'd63) begin
            cnt <= '0;
            state <= S_IN;
          end else cnt <= cnt + 7'd1;
        end
      endcase
    end
  end
endmodule
