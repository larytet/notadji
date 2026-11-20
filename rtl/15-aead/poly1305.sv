// poly1305 - one-time authenticator, full 16-byte blocks, 8-bit digit sequential multiplier (design/15-aead.md section 3).
// Blocks and keys are little-endian numbers (byte k in bits 8k+7..8k). Each block gets the 2^128 bit added.
module poly1305 (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         init,         // clears the accumulator and loads r (already clamped) and s
    input  logic [127:0] r_in,
    input  logic [127:0] s_in,
    input  logic         blk_valid,    // accept a 16-byte block (only while ready)
    input  logic [127:0] blk,
    output logic         ready,
    input  logic         fin,          // compute the tag (only while ready)
    output logic         tag_valid,    // one-clock pulse
    output logic [127:0] tag
);
  localparam logic [130:0] P = (131'd1 << 130) - 131'd5;

  logic [131:0] acc;
  logic [127:0] r, s;
  logic [135:0] a;
  logic [130:0] t;
  logic [4:0]   idx;
  logic         busy;
  logic         finish;

  assign ready = ~busy & ~finish;

  wire [7:0]   digit = a[8*idx +: 8];
  wire [139:0] prod  = {4'b0, digit} * {12'b0, r};
  wire [140:0] sum   = {2'b00, t, 8'b0} + {1'b0, prod};
  wire [130:0] folded = {1'b0, sum[129:0]} + (131'(sum[140:130]) * 131'd5);

  // final reduction
  wire [130:0] f1 = {1'b0, acc[129:0]} + (131'(acc[131:130]) * 131'd5);
  wire [130:0] f2 = (f1 >= P) ? (f1 - P) : f1;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      busy      <= 1'b0;
      finish    <= 1'b0;
      tag_valid <= 1'b0;
      acc       <= '0;
    end else begin
      tag_valid <= 1'b0;
      if (init) begin
        r   <= r_in;
        s   <= s_in;
        acc <= '0;
      end else if (blk_valid && ready) begin
        a    <= {4'b0, acc} + {8'b0, blk} + (136'd1 << 128);
        t    <= '0;
        idx  <= 5'd16;
        busy <= 1'b1;
      end else if (busy) begin
        t <= folded;
        if (idx == 5'd0) begin
          acc  <= {1'b0, folded};
          busy <= 1'b0;
        end else idx <= idx - 5'd1;
      end else if (fin && ready) begin
        finish <= 1'b1;
      end else if (finish) begin
        tag       <= f2[127:0] + s;
        tag_valid <= 1'b1;
        finish    <= 1'b0;
      end
    end
  end

  wire unused_ok = &{1'b0, f2[130:128], sum[140:140]};
endmodule
