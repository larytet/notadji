// gray_cnt_sync - saturating event counter in one clock domain, read safely in another (design/11-radio-interface.md section 2).
module gray_cnt_sync (
    input  logic        src_clk,
    input  logic        src_rst_n,
    input  logic        inc,
    input  logic        dst_clk,
    input  logic        dst_rst_n,
    output logic [15:0] cnt_dst
);
  logic [15:0] bin_s, gray_s;
  logic [15:0] g1, g2;

  always_ff @(posedge src_clk) begin
    if (!src_rst_n) begin
      bin_s  <= '0;
      gray_s <= '0;
    end else if (inc && bin_s != 16'hFFFF) begin
      bin_s  <= bin_s + 16'd1;
      gray_s <= ((bin_s + 16'd1) >> 1) ^ (bin_s + 16'd1);
    end
  end

  always_ff @(posedge dst_clk) begin
    if (!dst_rst_n) begin
      g1 <= '0;
      g2 <= '0;
    end else begin
      g1 <= gray_s;
      g2 <= g1;
    end
  end

  // Gray to binary by prefix XOR
  wire [15:0] d1 = g2 ^ (g2 >> 1);
  wire [15:0] d2 = d1 ^ (d1 >> 2);
  wire [15:0] d3 = d2 ^ (d2 >> 4);
  assign cnt_dst = d3 ^ (d3 >> 8);
endmodule
