// block_interleaver - 16-column block interleaver / de-interleaver (design/05-interleaver.md).
module block_interleaver #(
    parameter int W     = 1,
    parameter int MAX_N = 4096,
    parameter bit DEINT = 1'b0
) (
    input  logic                       clk,
    input  logic                       rst_n,
    input  logic [$clog2(MAX_N+1)-1:0] n,
    input  logic                       s_axis_valid,
    output logic                       s_axis_ready,
    input  logic [W-1:0]               s_axis_data,
    input  logic                       s_axis_last,
    output logic                       m_axis_valid,
    input  logic                       m_axis_ready,
    output logic [W-1:0]               m_axis_data,
    output logic                       m_axis_last,
    output logic [$clog2(MAX_N+1)-1:0] m_n,
    output logic                       err_len
);
  localparam int NW = $clog2(MAX_N + 1);
  localparam int AW = $clog2(MAX_N);

  logic [W-1:0] mem[2*(2**AW)];

  logic [1:0]    full;
  logic [NW-1:0] bank_n[2];

  // clamp n to 1..MAX_N
  wire [NW-1:0] n_cl = (n == '0) ? NW'(1) : (n > NW'(MAX_N)) ? NW'(MAX_N) : n;

  // ---------------- write side ----------------
  logic          wr_bank;
  logic [NW-1:0] wr_cnt;
  logic [NW-1:0] wr_n_q;
  wire  [NW-1:0] wr_n   = (wr_cnt == '0) ? n_cl : wr_n_q;
  wire           at_last = (wr_cnt == wr_n - 1'b1);

  assign s_axis_ready = ~full[wr_bank];
  wire wr_xfer = s_axis_valid & s_axis_ready;

  // ---------------- read side ----------------
  logic          rd_bank;
  logic [NW-1:0] rd_cnt;
  wire  [NW-1:0] rd_n    = bank_n[rd_bank];
  wire           rd_last = (rd_cnt == rd_n - 1'b1);

  assign m_axis_valid = full[rd_bank];
  assign m_axis_last  = rd_last;
  assign m_n          = rd_n;
  wire rd_xfer = m_axis_valid & m_axis_ready;

  logic [AW-1:0] wr_addr, rd_addr;

  generate
    if (!DEINT) begin : g_int
      logic gen_last;
      il_addr_gen #(.MAX_N(MAX_N)) u_gen (
          .clk(clk), .rst_n(rst_n), .n_eff(wr_n), .step(wr_xfer), .addr(wr_addr), .last(gen_last)
      );
      assign rd_addr = AW'(rd_cnt);
      wire unused_g = gen_last;
    end else begin : g_deint
      logic gen_last;
      il_addr_gen #(.MAX_N(MAX_N)) u_gen (
          .clk(clk), .rst_n(rst_n), .n_eff(rd_n), .step(rd_xfer), .addr(rd_addr), .last(gen_last)
      );
      assign wr_addr = AW'(wr_cnt);
      wire unused_g = gen_last;
    end
  endgenerate

  assign m_axis_data = mem[{rd_bank, rd_addr}];

  always_ff @(posedge clk) begin
    if (wr_xfer) mem[{wr_bank, wr_addr}] <= s_axis_data;
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      full    <= 2'b00;
      wr_bank <= 1'b0;
      wr_cnt  <= '0;
      rd_bank <= 1'b0;
      rd_cnt  <= '0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      if (wr_xfer) begin
        if (wr_cnt == '0) wr_n_q <= wr_n;
        if (s_axis_last != at_last) err_len <= 1'b1;
        if (at_last) begin
          full[wr_bank]   <= 1'b1;
          bank_n[wr_bank] <= wr_n;
          wr_bank         <= ~wr_bank;
          wr_cnt          <= '0;
        end else begin
          wr_cnt <= wr_cnt + 1'b1;
        end
      end
      if (rd_xfer) begin
        if (rd_last) begin
          full[rd_bank] <= 1'b0;
          rd_bank       <= ~rd_bank;
          rd_cnt        <= '0;
        end else begin
          rd_cnt <= rd_cnt + 1'b1;
        end
      end
    end
  end
endmodule
