// spi_master - mode 0, MSB first, queued commands with read-back (design/11-radio-interface.md section 3).
module spi_master (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  div,          // system clocks per half SCLK period, at least 1
    input  logic [5:0]  nbits,        // 1..32
    input  logic        s_axis_valid, // command word, low nbits bits are sent
    output logic        s_axis_ready,
    input  logic [31:0] s_axis_data,
    output logic        m_axis_valid, // response word, right-aligned
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic        sclk,
    output logic        mosi,
    output logic        cs_n,
    input  logic        miso,
    output logic        busy
);
  // command and response FIFOs
  logic        c_v, c_r, c_l;
  logic [31:0] c_d;
  logic [3:0]  c_level;
  axis_fifo #(.W(32), .DEPTH(8)) u_cmd (
      .clk(clk), .rst_n(rst_n), .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready), .s_axis_data(s_axis_data), .s_axis_last(1'b0),
      .m_axis_valid(c_v), .m_axis_ready(c_r), .m_axis_data(c_d), .m_axis_last(c_l), .level(c_level));

  logic        r_v, r_l, r_ready;
  logic [31:0] r_d;
  logic [3:0]  r_level;
  axis_fifo #(.W(32), .DEPTH(8)) u_rsp (
      .clk(clk), .rst_n(rst_n), .s_axis_valid(r_v), .s_axis_ready(r_ready), .s_axis_data(r_d), .s_axis_last(1'b0),
      .m_axis_valid(m_axis_valid), .m_axis_ready(m_axis_ready), .m_axis_data(m_axis_data), .m_axis_last(r_l), .level(r_level));

  typedef enum logic [1:0] {IDLE, SETUP, FRAME, GAP} state_t;
  state_t state;
  logic [7:0]  hc;
  logic [5:0]  bi;
  logic [31:0] sh, rxsh;
  logic        sclk_r;

  wire [5:0] nb = (nbits == 6'd0) ? 6'd1 : (nbits > 6'd32) ? 6'd32 : nbits;
  wire [7:0] dv = (div == 8'd0) ? 8'd1 : div;
  wire [4:0] nbm1 = 5'(nb - 6'd1);

  assign sclk = sclk_r;
  assign busy = (state != IDLE);
  assign c_r  = (state == IDLE) & r_ready;      // start a frame only when the response FIFO has room

  wire [31:0] mask = (nb == 6'd32) ? 32'hFFFF_FFFF : ((32'd1 << nb) - 32'd1);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state  <= IDLE;
      cs_n   <= 1'b1;
      sclk_r <= 1'b0;
      mosi   <= 1'b0;
      hc     <= '0;
      bi     <= '0;
      r_v    <= 1'b0;
    end else begin
      r_v <= 1'b0;
      case (state)
        IDLE: if (c_v & r_ready) begin
          sh     <= c_d << (6'd32 - nb);
          mosi   <= c_d[nbm1];
          cs_n   <= 1'b0;
          sclk_r <= 1'b0;
          hc     <= dv - 8'd1;
          bi     <= '0;
          state  <= SETUP;
        end
        SETUP: begin           // chip-select set-up: one half period before the first rising edge
          if (hc == 8'd0) begin
            hc    <= dv - 8'd1;
            state <= FRAME;
          end else hc <= hc - 8'd1;
        end
        FRAME: begin
          if (hc == 8'd0) begin
            hc <= dv - 8'd1;
            if (!sclk_r) begin       // rising edge: sample MISO
              sclk_r <= 1'b1;
              rxsh   <= {rxsh[30:0], miso};
            end else begin           // falling edge: next bit or end
              sclk_r <= 1'b0;
              bi     <= bi + 6'd1;
              if (bi == nb - 6'd1) begin
                cs_n  <= 1'b1;
                mosi  <= 1'b0;
                r_v   <= 1'b1;
                r_d   <= rxsh & mask;
                state <= GAP;
                hc    <= {dv[6:0], 1'b0} - 8'd1;     // two half periods of chip select high
              end else begin
                mosi <= sh[30];
                sh   <= {sh[30:0], 1'b0};
              end
            end
          end else hc <= hc - 8'd1;
        end
        default: begin   // GAP
          if (hc == 8'd0) state <= IDLE;
          else hc <= hc - 8'd1;
        end
      endcase
    end
  end

  wire unused_ok = &{1'b0, c_l, c_level, r_l, r_level, sh[31]};
endmodule
