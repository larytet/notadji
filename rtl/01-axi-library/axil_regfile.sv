// axil_regfile - AXI-Lite slave register file (design/01-axi-library.md section 3.5).
// Write to a read-only register: OKAY, ignored, no wr_pulse. Out of range: SLVERR, reads return 0.
module axil_regfile #(
    parameter int                N            = 16,
    parameter int                ADDR_W       = 8,
    parameter logic [N-1:0]      RO_MASK      = '0,
    parameter logic [N*32-1:0]   RESET_VALUES = '0
) (
    input  logic                 clk,
    input  logic                 rst_n,

    input  logic [ADDR_W-1:0]    awaddr,
    input  logic                 awvalid,
    output logic                 awready,
    input  logic [31:0]          wdata,
    input  logic [3:0]           wstrb,
    input  logic                 wvalid,
    output logic                 wready,
    output logic [1:0]           bresp,
    output logic                 bvalid,
    input  logic                 bready,

    input  logic [ADDR_W-1:0]    araddr,
    input  logic                 arvalid,
    output logic                 arready,
    output logic [31:0]          rdata,
    output logic [1:0]           rresp,
    output logic                 rvalid,
    input  logic                 rready,

    input  logic [N*32-1:0]      ro_data,
    output logic [N*32-1:0]      rw_data,
    output logic [N-1:0]         wr_pulse
);
  localparam int IW = ADDR_W - 2;
  localparam int NI = (N > 1) ? $clog2(N) : 1;  // ADDR_W must be at least NI + 2

  logic [31:0] regs[N];

  // write channel
  logic aw_got, w_got;
  logic [ADDR_W-1:0] awaddr_q;
  logic [31:0] wdata_q;
  logic [3:0] wstrb_q;

  assign awready = ~aw_got & ~bvalid;
  assign wready  = ~w_got & ~bvalid;

  wire [IW-1:0] widx    = awaddr_q[ADDR_W-1:2];
  wire          w_inrng = (widx < IW'(N));
  wire [NI-1:0] wsel    = widx[NI-1:0];
  wire          do_wr   = aw_got & w_got & ~bvalid;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      aw_got   <= 1'b0;
      w_got    <= 1'b0;
      bvalid   <= 1'b0;
      bresp    <= 2'b00;
      wr_pulse <= '0;
      for (int i = 0; i < N; i++) regs[i] <= RESET_VALUES[i*32+:32];
    end else begin
      wr_pulse <= '0;
      if (awvalid & awready) begin
        aw_got   <= 1'b1;
        awaddr_q <= awaddr;
      end
      if (wvalid & wready) begin
        w_got   <= 1'b1;
        wdata_q <= wdata;
        wstrb_q <= wstrb;
      end
      if (do_wr) begin
        aw_got <= 1'b0;
        w_got  <= 1'b0;
        bvalid <= 1'b1;
        bresp  <= w_inrng ? 2'b00 : 2'b10;
        if (w_inrng && !RO_MASK[wsel]) begin
          for (int b = 0; b < 4; b++) begin
            if (wstrb_q[b]) regs[wsel][b*8+:8] <= wdata_q[b*8+:8];
          end
          wr_pulse[wsel] <= 1'b1;
        end
      end
      if (bvalid & bready) bvalid <= 1'b0;
    end
  end

  // read channel
  wire [IW-1:0] ridx    = araddr[ADDR_W-1:2];
  wire [NI-1:0] rsel    = ridx[NI-1:0];
  wire          r_inrng = (ridx < IW'(N));

  assign arready = ~rvalid;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      rvalid <= 1'b0;
      rdata  <= '0;
      rresp  <= 2'b00;
    end else begin
      if (arvalid & arready) begin
        rvalid <= 1'b1;
        rresp  <= r_inrng ? 2'b00 : 2'b10;
        rdata  <= !r_inrng ? 32'h0 : RO_MASK[rsel] ? ro_data[rsel*32+:32] : regs[rsel];
      end
      if (rvalid & rready) rvalid <= 1'b0;
    end
  end

  always_comb begin
    for (int i = 0; i < N; i++) rw_data[i*32+:32] = regs[i];
  end
  // word-aligned registers: the two low address bits are ignored on purpose
  wire unused_ok = &{1'b0, araddr[1:0], awaddr_q[1:0]};
endmodule
