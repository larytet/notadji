// rx_framer - places the FFT windows after the STF end marker (design/21-rx-chain.md section 1).
module rx_framer #(
    parameter int BIAS = 2                  // mean marker error of module 18 (samples)
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  fft_log2,
    input  logic [1:0]  cp_sel,
    input  logic [3:0]  backoff,
    input  logic [7:0]  k_back,
    input  logic [15:0] nwin,               // number of windows (2 long training + data symbols)
    input  logic        fall,               // from the synchroniser, refers to the most recent sample
    input  logic        rearm,
    input  logic        s_valid,
    input  logic [31:0] s_data,
    output logic        m_valid,
    output logic [31:0] m_data,
    output logic        m_last,
    output logic        err_skip,           // sticky: the computed skip was negative
    output logic        active
);
  typedef enum logic [2:0] {S_IDLE, S_SKIP, S_TAKE, S_GAP, S_DONE} state_t;
  state_t state;

  wire [3:0]  l_cl = (fft_log2 < 4'd6) ? 4'd6 : (fft_log2 > 4'd9) ? 4'd9 : fft_log2;
  wire [10:0] n    = 11'd1 << l_cl;
  wire [2:0]  sh   = (cp_sel == 2'd0) ? 3'd4 : (cp_sel == 2'd1) ? 3'd3 : 3'd2;
  wire [10:0] lc   = n >> sh;
  wire signed [12:0] skip_s = $signed({2'b00, lc}) - $signed({9'b0, backoff}) - $signed({5'b0, k_back}) - 13'sd1 - 13'(BIAS);
  wire [10:0] skip = skip_s[12] ? 11'd0 : skip_s[10:0];

  logic [10:0] cnt;
  logic [15:0] wins;

  assign active  = (state != S_IDLE);
  assign m_valid = s_valid & (state == S_TAKE);
  assign m_data  = s_data;
  assign m_last  = (cnt == n - 11'd1);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state    <= S_IDLE;
      cnt      <= '0;
      wins     <= '0;
      err_skip <= 1'b0;
    end else begin
      if (rearm) begin
        state <= S_IDLE;
        cnt   <= '0;
      end else begin
        case (state)
          S_IDLE: if (fall) begin
            wins <= nwin;
            if (skip_s[12]) err_skip <= 1'b1;
            if (skip == 11'd0) begin
              state <= S_TAKE;
              cnt   <= '0;
            end else begin
              state <= S_SKIP;
              cnt   <= skip;
            end
          end
          S_SKIP: if (s_valid) begin
            if (cnt == 11'd1) begin
              state <= S_TAKE;
              cnt   <= '0;
            end else cnt <= cnt - 11'd1;
          end
          S_TAKE: if (s_valid) begin
            if (cnt == n - 11'd1) begin
              cnt  <= '0;
              wins <= wins - 16'd1;
              state <= (wins == 16'd1) ? S_DONE : S_GAP;
            end else cnt <= cnt + 11'd1;
          end
          S_GAP: if (s_valid) begin
            if (cnt == lc - 11'd1) begin
              state <= S_TAKE;
              cnt   <= '0;
            end else cnt <= cnt + 11'd1;
          end
          default: ;
        endcase
      end
    end
  end
  wire unused_ok = &{1'b0, skip_s[11]};
endmodule
