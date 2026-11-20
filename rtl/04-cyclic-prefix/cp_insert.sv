// cp_insert - cyclic-prefix insertion with a two-bank buffer (design/04-cyclic-prefix.md section 3).
module cp_insert #(
    parameter int W        = 32,
    parameter int MAX_LOG2 = 9
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [3:0]   fft_log2,
    input  logic [1:0]   cp_sel,
    input  logic         s_axis_valid,
    output logic         s_axis_ready,
    input  logic [W-1:0] s_axis_data,
    input  logic         s_axis_last,
    output logic         m_axis_valid,
    input  logic         m_axis_ready,
    output logic [W-1:0] m_axis_data,
    output logic         m_axis_last,
    output logic         err_len
);
  localparam int AW = MAX_LOG2;

  function automatic [3:0] clamp_log2(input [3:0] v);
    begin
      if (v < 4'd6) clamp_log2 = 4'd6;
      else if (v > 4'(MAX_LOG2)) clamp_log2 = 4'(MAX_LOG2);
      else clamp_log2 = v;
    end
  endfunction

  function automatic [2:0] shift_of(input [1:0] sel);
    begin
      shift_of = (sel == 2'd0) ? 3'd4 : (sel == 2'd1) ? 3'd3 : 3'd2;
    end
  endfunction

  logic [W-1:0] mem[2*(2**AW)];

  logic [1:0]   full;
  logic [3:0]   bank_log2[2];
  logic [2:0]   bank_sh[2];

  // ---------------- write side ----------------
  logic          wr_bank;
  logic [AW-1:0] wr_idx;
  logic [3:0]    wr_log2_q;
  logic [2:0]    wr_sh_q;

  wire [3:0]    cur_log2 = (wr_idx == '0) ? clamp_log2(fft_log2) : wr_log2_q;
  wire [2:0]    cur_sh   = (wr_idx == '0) ? shift_of(cp_sel) : wr_sh_q;
  wire [AW-1:0] last_idx = AW'((1 << cur_log2) - 1);
  wire          at_last  = (wr_idx == last_idx);

  assign s_axis_ready = ~full[wr_bank];
  wire wr_xfer = s_axis_valid & s_axis_ready;

  // ---------------- read side ----------------
  logic          rd_bank;
  logic [AW+1:0] k;

  wire [AW:0]   rd_n     = (AW + 1)'(1) << bank_log2[rd_bank];
  wire [AW:0]   rd_l     = rd_n >> bank_sh[rd_bank];
  wire [AW+1:0] rd_total = {1'b0, rd_n} + {1'b0, rd_l};
  wire [AW+1:0] k_l      = {1'b0, rd_l};
  wire [AW-1:0] addr     = (k < k_l) ? AW'(rd_n - rd_l + k[AW:0]) : AW'(k[AW:0] - rd_l);
  wire          rd_last  = (k == rd_total - 1'b1);

  assign m_axis_valid = full[rd_bank];
  assign m_axis_data  = mem[{rd_bank, addr}];
  assign m_axis_last  = rd_last;
  wire rd_xfer = m_axis_valid & m_axis_ready;

  always_ff @(posedge clk) begin
    if (wr_xfer) mem[{wr_bank, wr_idx}] <= s_axis_data;
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      full    <= 2'b00;
      wr_bank <= 1'b0;
      wr_idx  <= '0;
      rd_bank <= 1'b0;
      k       <= '0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      if (wr_xfer) begin
        if (wr_idx == '0) begin
          wr_log2_q <= cur_log2;
          wr_sh_q   <= cur_sh;
        end
        if (s_axis_last != at_last) err_len <= 1'b1;
        if (at_last) begin
          full[wr_bank]      <= 1'b1;
          bank_log2[wr_bank] <= cur_log2;
          bank_sh[wr_bank]   <= cur_sh;
          wr_bank            <= ~wr_bank;
          wr_idx             <= '0;
        end else begin
          wr_idx <= wr_idx + 1'b1;
        end
      end
      if (rd_xfer) begin
        if (rd_last) begin
          full[rd_bank] <= 1'b0;
          rd_bank       <= ~rd_bank;
          k             <= '0;
        end else begin
          k <= k + 1'b1;
        end
      end
    end
  end
endmodule
