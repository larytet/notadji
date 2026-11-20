// slice_pack - slice frame builder: header, payload, CRC-32 (design/09-slice-packetiser.md section 2).
module slice_pack #(
    parameter int MAX_BYTES = 4096    // power of two
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] meta_frame,
    input  logic [7:0]  meta_idx,
    input  logic [3:0]  meta_flags,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [7:0]  m_axis_data,
    output logic        m_axis_last
);
  localparam int PW = $clog2(MAX_BYTES) + 1;

  function automatic [15:0] crc16_6(input [47:0] v);
    reg [15:0] c;
    integer i, k;
    begin
      c = 16'hFFFF;
      for (i = 0; i < 6; i = i + 1) begin
        c = c ^ ({8'h00, v[8*i+:8]} << 8);
        for (k = 0; k < 8; k = k + 1) c = c[15] ? ((c << 1) ^ 16'h1021) : (c << 1);
      end
      crc16_6 = c;
    end
  endfunction

  // ---------------- input side ----------------
  logic        in_first;
  logic [15:0] in_cnt;
  logic [15:0] cap_frame;
  logic [7:0]  cap_idx;
  logic [3:0]  cap_flags;

  logic        pf_ready, rec_ready;
  assign s_axis_ready = pf_ready & rec_ready;
  wire in_xfer = s_axis_valid & s_axis_ready;

  wire [15:0] fr_now = in_first ? meta_frame : cap_frame;
  wire [7:0]  ix_now = in_first ? meta_idx   : cap_idx;
  wire [3:0]  fl_now = in_first ? meta_flags : cap_flags;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      in_first <= 1'b1;
      in_cnt   <= '0;
    end else if (in_xfer) begin
      if (in_first) begin
        cap_frame <= meta_frame;
        cap_idx   <= meta_idx;
        cap_flags <= meta_flags;
      end
      if (s_axis_last) begin
        in_first <= 1'b1;
        in_cnt   <= '0;
      end else begin
        in_first <= 1'b0;
        in_cnt   <= in_cnt + 16'd1;
      end
    end
  end

  logic       pf_v, pf_r, pf_l;
  logic [7:0] pf_d;
  logic [PW-1:0] pf_level;
  axis_fifo #(.W(8), .DEPTH(MAX_BYTES)) u_pf (
      .clk(clk), .rst_n(rst_n),
      .s_axis_valid(s_axis_valid & rec_ready), .s_axis_ready(pf_ready), .s_axis_data(s_axis_data), .s_axis_last(1'b0),
      .m_axis_valid(pf_v), .m_axis_ready(pf_r), .m_axis_data(pf_d), .m_axis_last(pf_l),
      .level(pf_level));

  // record FIFO: {len, frame, idx, flags}
  logic        rec_v, rec_r, rec_l;
  logic [43:0] rec_d;
  logic [2:0]  rec_level;
  axis_fifo #(.W(44), .DEPTH(4)) u_rec (
      .clk(clk), .rst_n(rst_n),
      .s_axis_valid(in_xfer & s_axis_last), .s_axis_ready(rec_ready),
      .s_axis_data({in_cnt + 16'd1, fr_now, ix_now, fl_now}), .s_axis_last(1'b0),
      .m_axis_valid(rec_v), .m_axis_ready(rec_r), .m_axis_data(rec_d), .m_axis_last(rec_l),
      .level(rec_level));

  // ---------------- output side ----------------
  typedef enum logic [1:0] {S_IDLE, S_HDR, S_PAY, S_CRC} state_t;
  state_t state;
  logic [15:0] r_len, r_frame;
  logic [7:0]  r_idx;
  logic [3:0]  r_flags;
  logic [15:0] ocnt;

  assign rec_r = (state == S_IDLE);

  wire [47:0] hdr6  = {r_len[15:8], r_len[7:0], r_idx, r_frame[15:8], r_frame[7:0], {4'h0, r_flags}};
  wire [15:0] hcrc  = crc16_6(hdr6);

  // payload through the CRC-32 engine
  logic        c_v, c_l;
  logic [7:0]  c_d;
  logic [31:0] crc_value;
  logic        crc_valid, crc_ok;
  wire         pay_last = (ocnt == r_len - 16'd1);
  crc_engine #(.DW(8)) u_crc (
      .clk(clk), .rst_n(rst_n),
      .s_axis_valid((state == S_PAY) & pf_v), .s_axis_ready(pf_r), .s_axis_data(pf_d), .s_axis_last(pay_last),
      .m_axis_valid(c_v), .m_axis_ready((state == S_PAY) & m_axis_ready), .m_axis_data(c_d), .m_axis_last(c_l),
      .crc_value(crc_value), .crc_valid(crc_valid), .crc_ok(crc_ok));

  logic [7:0] hdr_byte;
  always_comb begin
    case (ocnt[2:0])
      3'd0: hdr_byte = {4'h0, r_flags};
      3'd1: hdr_byte = r_frame[7:0];
      3'd2: hdr_byte = r_frame[15:8];
      3'd3: hdr_byte = r_idx;
      3'd4: hdr_byte = r_len[7:0];
      3'd5: hdr_byte = r_len[15:8];
      3'd6: hdr_byte = hcrc[15:8];
      default: hdr_byte = hcrc[7:0];
    endcase
  end

  wire [31:0] crc_out = (r_len == 16'd0) ? 32'd0 : crc_value;
  logic [7:0] crc_byte;
  always_comb begin
    case (ocnt[1:0])
      2'd0: crc_byte = crc_out[7:0];
      2'd1: crc_byte = crc_out[15:8];
      2'd2: crc_byte = crc_out[23:16];
      default: crc_byte = crc_out[31:24];
    endcase
  end

  always_comb begin
    case (state)
      S_HDR:   begin m_axis_valid = 1'b1; m_axis_data = hdr_byte; m_axis_last = 1'b0; end
      S_PAY:   begin m_axis_valid = c_v;  m_axis_data = c_d;      m_axis_last = 1'b0; end
      S_CRC:   begin m_axis_valid = 1'b1; m_axis_data = crc_byte; m_axis_last = (ocnt[1:0] == 2'd3); end
      default: begin m_axis_valid = 1'b0; m_axis_data = 8'h00;    m_axis_last = 1'b0; end
    endcase
  end

  wire out_xfer = m_axis_valid & m_axis_ready;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state <= S_IDLE;
      ocnt  <= '0;
    end else begin
      case (state)
        S_IDLE: if (rec_v) begin
          {r_len, r_frame, r_idx, r_flags} <= rec_d;
          state <= S_HDR;
          ocnt  <= '0;
        end
        S_HDR: if (out_xfer) begin
          if (ocnt[2:0] == 3'd7) begin
            ocnt  <= '0;
            state <= (r_len == 16'd0) ? S_CRC : S_PAY;
          end else begin
            ocnt <= ocnt + 16'd1;
          end
        end
        S_PAY: if (out_xfer) begin
          if (pay_last) begin
            ocnt  <= '0;
            state <= S_CRC;
          end else begin
            ocnt <= ocnt + 16'd1;
          end
        end
        default: if (out_xfer) begin       // S_CRC
          if (ocnt[1:0] == 2'd3) state <= S_IDLE;
          ocnt <= ocnt + 16'd1;
        end
      endcase
    end
  end

  wire unused_ok = &{1'b0, pf_l, pf_level, rec_l, rec_level, crc_valid, crc_ok, c_l};
endmodule
