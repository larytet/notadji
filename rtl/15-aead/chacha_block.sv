// chacha_block - sequential ChaCha20 block function, one quarter round per clock (design/15-aead.md section 3).
// key, nonce: little-endian byte strings (byte k in bits 8k+7..8k). ks: 64 keystream bytes, byte k in bits 8k+7..8k.
module chacha_block (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start,
    input  logic [255:0] key,
    input  logic [95:0]  nonce,
    input  logic [31:0]  counter,
    output logic         busy,
    output logic         done,       // one-clock pulse; ks valid in that clock and held until the next start
    output logic [511:0] ks
);
  function automatic [127:0] qr(input [31:0] a, input [31:0] b, input [31:0] c, input [31:0] d);
    reg [31:0] a1, b1, c1, d1;
    begin
      a1 = a + b;  d1 = d ^ a1;  d1 = {d1[15:0], d1[31:16]};
      c1 = c + d1; b1 = b ^ c1;  b1 = {b1[19:0], b1[31:20]};
      a1 = a1 + b1; d1 = d1 ^ a1; d1 = {d1[23:0], d1[31:24]};
      c1 = c1 + d1; b1 = b1 ^ c1; b1 = {b1[24:0], b1[31:25]};
      qr = {a1, b1, c1, d1};
    end
  endfunction

  logic [31:0] x[16];
  logic [31:0] ini[16];
  logic [6:0]  step;

  // quarter round selection: steps 0..79; within a double round (8 steps) 4 column then 4 diagonal
  logic [3:0] ia, ib, ic, id;
  always_comb begin
    case (step[2:0])
      3'd0: begin ia = 4'd0; ib = 4'd4; ic = 4'd8;  id = 4'd12; end
      3'd1: begin ia = 4'd1; ib = 4'd5; ic = 4'd9;  id = 4'd13; end
      3'd2: begin ia = 4'd2; ib = 4'd6; ic = 4'd10; id = 4'd14; end
      3'd3: begin ia = 4'd3; ib = 4'd7; ic = 4'd11; id = 4'd15; end
      3'd4: begin ia = 4'd0; ib = 4'd5; ic = 4'd10; id = 4'd15; end
      3'd5: begin ia = 4'd1; ib = 4'd6; ic = 4'd11; id = 4'd12; end
      3'd6: begin ia = 4'd2; ib = 4'd7; ic = 4'd8;  id = 4'd13; end
      default: begin ia = 4'd3; ib = 4'd4; ic = 4'd9; id = 4'd14; end
    endcase
  end

  wire [127:0] q = qr(x[ia], x[ib], x[ic], x[id]);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      busy <= 1'b0;
      done <= 1'b0;
      step <= '0;
    end else begin
      done <= 1'b0;
      if (start && !busy) begin
        ini[0] <= 32'h61707865; ini[1] <= 32'h3320646e; ini[2] <= 32'h79622d32; ini[3] <= 32'h6b206574;
        for (int i = 0; i < 8; i++) ini[4 + i] <= key[32*i +: 32];
        ini[12] <= counter;
        for (int i = 0; i < 3; i++) ini[13 + i] <= nonce[32*i +: 32];
        x[0] <= 32'h61707865; x[1] <= 32'h3320646e; x[2] <= 32'h79622d32; x[3] <= 32'h6b206574;
        for (int i = 0; i < 8; i++) x[4 + i] <= key[32*i +: 32];
        x[12] <= counter;
        for (int i = 0; i < 3; i++) x[13 + i] <= nonce[32*i +: 32];
        step <= '0;
        busy <= 1'b1;
      end else if (busy) begin
        if (step == 7'd80) begin
          for (int i = 0; i < 16; i++) ks[32*i +: 32] <= x[i] + ini[i];
          busy <= 1'b0;
          done <= 1'b1;
        end else begin
          x[ia] <= q[127:96];
          x[ib] <= q[95:64];
          x[ic] <= q[63:32];
          x[id] <= q[31:0];
          step  <= step + 7'd1;
        end
      end
    end
  end
endmodule
