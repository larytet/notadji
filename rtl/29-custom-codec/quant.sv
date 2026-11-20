// quant - quantiser of one coefficient (design/29-custom-codec.md section 1): level = sign(c) ((|c| r + f) >> 16).
module quant (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        s_valid,
    input  logic signed [15:0] coef,
    input  logic [15:0] recip,                  // round(65536 / step)
    input  logic [15:0] rnd,                    // rounding offset f (Q16)
    output logic        m_valid,
    output logic signed [15:0] level
);
  wire [15:0] mag = coef[15] ? 16'(-coef) : coef[15:0];
  wire [31:0] prod = {16'd0, mag} * {16'd0, recip} + {16'd0, rnd};
  wire [15:0] q = prod[31:16];
  wire unused_ok = &{1'b0, prod[15:0]};
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      m_valid <= 1'b0;
      level <= '0;
    end else begin
      m_valid <= s_valid;
      level <= (coef[15] && q != 16'd0) ? -$signed(q) : $signed(q);
    end
  end
endmodule
