// uart_tx - 8N1 transmitter, runtime bit period (design/08-telemetry-bridge.md section 2.2).
module uart_tx (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] div,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,
    output logic        txd,
    output logic        busy
);
  logic [9:0]  sh;
  logic [3:0]  bitn;
  logic [15:0] cnt;

  wire bit_end = busy && (cnt == 16'd0);
  assign s_axis_ready = ~busy | (bit_end && bitn == 4'd9);
  wire xfer = s_axis_valid & s_axis_ready;

  assign txd = busy ? sh[0] : 1'b1;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      busy <= 1'b0;
      sh   <= '1;
      bitn <= '0;
      cnt  <= '0;
    end else begin
      if (busy) begin
        if (cnt == 16'd0) begin
          cnt <= div - 16'd1;
          sh  <= {1'b1, sh[9:1]};
          if (bitn == 4'd9) busy <= 1'b0;
          bitn <= bitn + 4'd1;
        end else begin
          cnt <= cnt - 16'd1;
        end
      end
      if (xfer) begin
        busy <= 1'b1;
        sh   <= {1'b1, s_axis_data, 1'b0};
        bitn <= 4'd0;
        cnt  <= div - 16'd1;
      end
    end
  end
endmodule
