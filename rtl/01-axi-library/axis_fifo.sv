// axis_fifo - synchronous first-word-fall-through FIFO (design/01-axi-library.md section 3.2).
module axis_fifo #(
    parameter int W     = 32,
    parameter int DEPTH = 16   // power of two, 2 or more
) (
    input  logic                     clk,
    input  logic                     rst_n,
    input  logic                     s_axis_valid,
    output logic                     s_axis_ready,
    input  logic [W-1:0]             s_axis_data,
    input  logic                     s_axis_last,
    output logic                     m_axis_valid,
    input  logic                     m_axis_ready,
    output logic [W-1:0]             m_axis_data,
    output logic                     m_axis_last,
    output logic [$clog2(DEPTH):0]   level
);
  localparam int AW = $clog2(DEPTH);

  logic [W:0] mem[DEPTH];
  logic [AW:0] wr_ptr, rd_ptr;

  wire empty = (wr_ptr == rd_ptr);
  wire full  = (wr_ptr[AW] != rd_ptr[AW]) && (wr_ptr[AW-1:0] == rd_ptr[AW-1:0]);

  assign s_axis_ready = ~full;
  assign m_axis_valid = ~empty;
  assign {m_axis_last, m_axis_data} = mem[rd_ptr[AW-1:0]];
  assign level = wr_ptr - rd_ptr;

  wire do_wr = s_axis_valid & ~full;
  wire do_rd = m_axis_ready & ~empty;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wr_ptr <= '0;
      rd_ptr <= '0;
    end else begin
      if (do_wr) wr_ptr <= wr_ptr + 1'b1;
      if (do_rd) rd_ptr <= rd_ptr + 1'b1;
    end
  end

  always_ff @(posedge clk) begin
    if (do_wr) mem[wr_ptr[AW-1:0]] <= {s_axis_last, s_axis_data};
  end
endmodule
