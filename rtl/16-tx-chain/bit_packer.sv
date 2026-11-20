// bit_packer - nb bits to one tone word, bit 0 first (design/16-tx-chain.md section 2).
module bit_packer (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [3:0] nb,
    input  logic       s_valid,
    output logic       s_ready,
    input  logic       s_data,
    input  logic       s_last,           // last bit of a block
    output logic       m_valid,
    input  logic       m_ready,
    output logic [7:0] m_data,
    output logic       m_last            // last tone of a block
);
  logic [3:0] cnt;
  logic [7:0] acc;
  logic       o_v, o_l;
  logic [7:0] o_d;

  wire can_out = ~o_v | m_ready;
  wire done    = (cnt == nb - 4'd1);
  wire [7:0] acc2 = acc | ({7'd0, s_data} << cnt[2:0]);

  assign s_ready = can_out;
  assign m_valid = o_v;
  assign m_data  = o_d;
  assign m_last  = o_l;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      cnt <= '0;
      acc <= '0;
      o_v <= 1'b0;
    end else begin
      if (o_v && m_ready) o_v <= 1'b0;
      if (s_valid && can_out) begin
        if (done) begin
          o_v <= 1'b1;
          o_d <= acc2;
          o_l <= s_last;
          acc <= 8'd0;
          cnt <= '0;
        end else begin
          acc <= acc2;
          cnt <= cnt + 4'd1;
        end
      end
    end
  end
endmodule
