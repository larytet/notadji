// tail_hold - delays a byte stream by 16 bytes and presents the last 16 bytes as a tag word (design/15-aead.md section 3).
module tail_hold (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         s_axis_valid,
    output logic         s_axis_ready,
    input  logic [7:0]   s_axis_data,
    input  logic         s_axis_last,
    output logic         m_axis_valid,
    input  logic         m_axis_ready,
    output logic [7:0]   m_axis_data,
    output logic         m_axis_last,    // on the last byte before the tag
    output logic [127:0] m_tail,         // valid with m_axis_last and with m_empty
    output logic         m_empty,        // one clock: frame of exactly 16 bytes (no payload)
    output logic         m_short         // one clock: frame shorter than 16 bytes
);
  logic [7:0] win[16];
  logic [4:0] cnt;
  wire full = (cnt == 5'd16);

  assign m_axis_valid = full & s_axis_valid;
  assign m_axis_data  = win[0];
  assign m_axis_last  = s_axis_last;
  assign s_axis_ready = full ? m_axis_ready : 1'b1;
  wire xfer = s_axis_valid & s_axis_ready;

  logic [127:0] tail_r;          // tag of a frame of exactly 16 bytes (held for the m_empty pulse)
  always_comb begin
    if (full) begin
      for (int i = 0; i < 15; i++) m_tail[8*i +: 8] = win[i + 1];
      m_tail[127:120] = s_axis_data;
    end else begin
      m_tail = tail_r;
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      cnt     <= '0;
      m_empty <= 1'b0;
      m_short <= 1'b0;
    end else begin
      m_empty <= 1'b0;
      m_short <= 1'b0;
      if (xfer) begin
        if (full) begin
          for (int i = 0; i < 15; i++) win[i] <= win[i + 1];
          win[15] <= s_axis_data;
          if (s_axis_last) cnt <= '0;
        end else begin
          win[cnt[3:0]] <= s_axis_data;
          if (s_axis_last) begin
            cnt <= '0;
            if (cnt == 5'd15) begin
              m_empty <= 1'b1;
              for (int i = 0; i < 15; i++) tail_r[8*i +: 8] <= win[i];
              tail_r[127:120] <= s_axis_data;
            end else m_short <= 1'b1;
          end else cnt <= cnt + 5'd1;
        end
      end
    end
  end
endmodule
