// crc_engine - parallel CRC, zero-latency pass-through (design/03-scrambler-crc.md section 4).
// Rocksoft parameter model: INIT, REFIN, REFOUT, XOROUT as in the CRC catalogue.
module crc_engine #(
    parameter int                CRC_W   = 32,
    parameter logic [CRC_W-1:0]  POLY    = 32'h04C11DB7,
    parameter logic [CRC_W-1:0]  INIT    = 32'hFFFFFFFF,
    parameter bit                REFIN   = 1'b1,
    parameter bit                REFOUT  = 1'b1,
    parameter logic [CRC_W-1:0]  XOROUT  = 32'hFFFFFFFF,
    parameter logic [CRC_W-1:0]  RESIDUE = 32'h2144DF1C,
    parameter int                DW      = 32            // multiple of 8
) (
    input  logic            clk,
    input  logic            rst_n,
    input  logic            s_axis_valid,
    output logic            s_axis_ready,
    input  logic [DW-1:0]   s_axis_data,
    input  logic            s_axis_last,
    output logic            m_axis_valid,
    input  logic            m_axis_ready,
    output logic [DW-1:0]   m_axis_data,
    output logic            m_axis_last,
    output logic [CRC_W-1:0] crc_value,
    output logic            crc_valid,
    output logic            crc_ok
);
  function automatic [CRC_W-1:0] rev(input [CRC_W-1:0] x);
    integer i;
    begin
      for (i = 0; i < CRC_W; i = i + 1) rev[i] = x[CRC_W-1-i];
    end
  endfunction

  localparam logic [CRC_W-1:0] RPOLY    = rev(POLY);
  localparam logic [CRC_W-1:0] REG_INIT = REFIN ? rev(INIT) : INIT;

  function automatic [CRC_W-1:0] step_byte(input [CRC_W-1:0] c, input [7:0] b);
    reg [CRC_W-1:0] r;
    integer k;
    begin
      r = c;
      if (REFIN) begin
        r = r ^ CRC_W'(b);
        for (k = 0; k < 8; k = k + 1) r = r[0] ? ((r >> 1) ^ RPOLY) : (r >> 1);
      end else begin
        r = r ^ (CRC_W'(b) << (CRC_W - 8));
        for (k = 0; k < 8; k = k + 1) r = r[CRC_W-1] ? ((r << 1) ^ POLY) : (r << 1);
      end
      step_byte = r;
    end
  endfunction

  function automatic [CRC_W-1:0] finalize(input [CRC_W-1:0] r);
    begin
      finalize = ((REFIN == REFOUT) ? r : rev(r)) ^ XOROUT;
    end
  endfunction

  logic [CRC_W-1:0] crc_reg, start, nxt;
  logic first;

  always_comb begin
    start = first ? REG_INIT : crc_reg;
    nxt   = start;
    for (int k = 0; k < DW / 8; k++) nxt = step_byte(nxt, s_axis_data[8*k+:8]);
  end

  assign m_axis_valid = s_axis_valid;
  assign s_axis_ready = m_axis_ready;
  assign m_axis_data  = s_axis_data;
  assign m_axis_last  = s_axis_last;

  wire xfer = s_axis_valid & m_axis_ready;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      crc_reg   <= REG_INIT;
      first     <= 1'b1;
      crc_valid <= 1'b0;
    end else begin
      crc_valid <= xfer & s_axis_last;
      if (xfer) begin
        crc_reg <= nxt;
        first   <= s_axis_last;
      end
    end
  end

  assign crc_value = finalize(crc_reg);
  assign crc_ok    = crc_valid && (crc_value == RESIDUE);
endmodule
