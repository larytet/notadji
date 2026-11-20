// il_addr_gen - generates pos(k) of the 16-column block interleaver incrementally (design/05-interleaver.md section 2).
// n_eff must be valid in every clock of the block (including the first). step advances to the next k.
module il_addr_gen #(
    parameter int MAX_N = 4096
) (
    input  logic                       clk,
    input  logic                       rst_n,
    input  logic [$clog2(MAX_N+1)-1:0] n_eff,
    input  logic                       step,
    output logic [$clog2(MAX_N)-1:0]   addr,
    output logic                       last
);
  localparam int NW = $clog2(MAX_N + 1);
  localparam int AW = $clog2(MAX_N);

  logic [3:0]    c;
  logic [NW-1:0] r;
  logic [AW-1:0] base;

  wire [NW-1:0] rows    = (n_eff + NW'(15)) >> 4;                 // R = ceil(n/16)
  wire [3:0]    full    = 4'((n_eff - 1'b1) & NW'(15)) + 4'd1;     // elements in the last row (16 wraps to 0 below)
  wire          full16  = (((n_eff - 1'b1) & NW'(15)) == NW'(15));
  wire [NW-1:0] full_n  = full16 ? NW'(16) : NW'(full);
  wire [NW-1:0] c_ext   = NW'(c);
  wire          c_lt_full = (c_ext < full_n);
  wire [AW-1:0] inc     = c_lt_full ? AW'(rows) : AW'(rows - 1'b1);

  assign addr = base + AW'(r);
  assign last = (r == rows - 1'b1) && (c_ext == full_n - 1'b1);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      c    <= '0;
      r    <= '0;
      base <= '0;
    end else if (step) begin
      if (last) begin
        c    <= '0;
        r    <= '0;
        base <= '0;
      end else if (c == 4'd15) begin
        c    <= '0;
        r    <= r + 1'b1;
        base <= '0;
      end else begin
        c    <= c + 1'b1;
        base <= base + inc;
      end
    end
  end
endmodule
