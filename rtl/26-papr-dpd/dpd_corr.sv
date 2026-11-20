// dpd_corr - correlation accumulation for the least-squares DPD fit (design/26-papr-dpd.md section 1.4).
// R[p][q] = sum conj(phi_p) phi_q (upper triangle, 45 entries), c[p] = sum conj(phi_p) u (9 entries); phi from y.
module dpd_corr (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        clear,
    input  logic [23:0] n_samples,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [31:0] y_data,
    input  logic [31:0] u_data,
    output logic        busy,
    output logic        done,
    output logic [23:0] count,
    input  logic [5:0]  rd_idx,
    output logic signed [47:0] rd_re,
    output logic signed [47:0] rd_im
);
  typedef enum logic [2:0] {S_IDLE, S_B1, S_B2, S_B3, S_ACC} state_t;
  state_t state;

  logic signed [15:0] xi, xq, ui, uq;
  logic [15:0]        r, r2;
  logic signed [15:0] bi [3][3];
  logic signed [15:0] bq [3][3];
  logic signed [47:0] ar [54];
  logic signed [47:0] ai [54];
  logic [3:0] p, q;
  logic       ph_c;
  logic [5:0] e;

  wire signed [31:0] ii = xi * xi;
  wire signed [31:0] qq = xq * xq;
  wire [31:0] m2 = 32'(ii) + 32'(qq);
  wire [16:0] r_full = m2[31:15];
  wire signed [32:0] pr2 = $signed({1'b0, r}) * $signed({1'b0, r});
  wire signed [15:0] rs  = $signed({1'b0, r[14:0]});
  wire signed [15:0] r2s = $signed({1'b0, r2[14:0]});

  // operands of the current entry
  logic signed [15:0] pa, pb, qc, qd;
  always_comb begin
    pa = bi[p/3][p%3];
    pb = bq[p/3][p%3];
    qc = ph_c ? ui : bi[q/3][q%3];
    qd = ph_c ? uq : bq[q/3][q%3];
  end
  // conj(a + jb) * (c + jd) = (ac + bd) + j(ad - bc)
  wire signed [32:0] pr = 33'(pa * qc) + 33'(pb * qd);
  wire signed [32:0] pi = 33'(pa * qd) - 33'(pb * qc);

  assign s_ready = (state == S_IDLE);
  assign busy = (state != S_IDLE);
  wire unused_ok = &{1'b0, r_full[16], pr2[32:31], pr2[14:0], r[15], r2[15], m2[14:0]};

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state <= S_IDLE;
      count <= '0;
      done <= 1'b0;
      p <= '0;
      q <= '0;
      e <= '0;
      ph_c <= 1'b0;
      xi <= '0;
      xq <= '0;
      ui <= '0;
      uq <= '0;
      r <= '0;
      r2 <= '0;
      rd_re <= '0;
      rd_im <= '0;
      /* verilator lint_off BLKSEQ */
      for (int k = 0; k < 54; k++) begin
        ar[k] = '0;
        ai[k] = '0;
      end
      for (int t = 0; t < 9; t++) begin
        bi[t/3][t%3] = '0;
        bq[t/3][t%3] = '0;
      end
      /* verilator lint_on BLKSEQ */
    end else begin
      done <= 1'b0;
      rd_re <= ar[rd_idx];
      rd_im <= ai[rd_idx];
      if (clear) begin
        count <= '0;
        /* verilator lint_off BLKSEQ */
        for (int k = 0; k < 54; k++) begin
          ar[k] = '0;
          ai[k] = '0;
        end
        for (int t = 0; t < 9; t++) begin
          bi[t/3][t%3] = '0;
          bq[t/3][t%3] = '0;
        end
        /* verilator lint_on BLKSEQ */
        state <= S_IDLE;
      end else begin
        case (state)
          S_IDLE: begin
            if (s_valid) begin
              xi <= y_data[15:0];
              xq <= y_data[31:16];
              ui <= u_data[15:0];
              uq <= u_data[31:16];
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
            p <= '0;
            q <= '0;
            e <= '0;
            ph_c <= 1'b0;
            state <= S_ACC;
          end
          default: begin
            ar[e] <= ar[e] + 48'(pr);
            ai[e] <= ai[e] + 48'(pi);
            e <= e + 6'd1;
            if (!ph_c) begin
              if (q == 4'd8) begin
                if (p == 4'd8) begin
                  ph_c <= 1'b1;
                  p <= '0;
                end else begin
                  p <= p + 4'd1;
                  q <= p + 4'd1;
                end
              end else q <= q + 4'd1;
            end else begin
              if (p == 4'd8) begin
                state <= S_IDLE;
                count <= count + 24'd1;
                if (n_samples != 24'd0 && count + 24'd1 == n_samples) done <= 1'b1;
              end else p <= p + 4'd1;
            end
          end
        endcase
      end
    end
  end
endmodule
