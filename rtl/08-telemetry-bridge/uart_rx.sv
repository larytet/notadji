// uart_rx - 8N1 receiver, runtime bit period (design/08-telemetry-bridge.md section 2.1).
module uart_rx (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] div,          // clocks per bit, at least 4
    input  logic        rxd,
    output logic        m_axis_valid, // one-clock pulse per received byte
    output logic [7:0]  m_axis_data,
    output logic        frame_err     // one-clock pulse with the byte when the stop bit was 0
);
  typedef enum logic [1:0] {IDLE, START, DATA, STOP} state_t;
  state_t state;

  logic rxd_s1, rxd_s2;
  logic [15:0] cnt;
  logic [2:0]  bitn;
  logic [7:0]  sh;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      rxd_s1       <= 1'b1;
      rxd_s2       <= 1'b1;
      state        <= IDLE;
      cnt          <= '0;
      bitn         <= '0;
      m_axis_valid <= 1'b0;
      frame_err    <= 1'b0;
    end else begin
      rxd_s1       <= rxd;
      rxd_s2       <= rxd_s1;
      m_axis_valid <= 1'b0;
      frame_err    <= 1'b0;
      case (state)
        IDLE: begin
          if (!rxd_s2) begin
            state <= START;
            cnt   <= (div >> 1) - 16'd1;
          end
        end
        START: begin
          if (cnt == 16'd0) begin
            if (!rxd_s2) begin
              state <= DATA;
              cnt   <= div - 16'd1;
              bitn  <= 3'd0;
            end else begin
              state <= IDLE;       // glitch: the line went back high before the middle of the start bit
            end
          end else begin
            cnt <= cnt - 16'd1;
          end
        end
        DATA: begin
          if (cnt == 16'd0) begin
            sh  <= {rxd_s2, sh[7:1]};
            cnt <= div - 16'd1;
            if (bitn == 3'd7) state <= STOP;
            bitn <= bitn + 3'd1;
          end else begin
            cnt <= cnt - 16'd1;
          end
        end
        default: begin   // STOP
          if (cnt == 16'd0) begin
            m_axis_valid <= 1'b1;
            frame_err    <= ~rxd_s2;
            state        <= IDLE;
          end else begin
            cnt <= cnt - 16'd1;
          end
        end
      endcase
    end
  end

  assign m_axis_data = sh;
endmodule
