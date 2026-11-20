// slice_unpack - slice frame parser: header check, cut-through payload, CRC-32 status (design/09-slice-packetiser.md section 3).
module slice_unpack #(
    parameter int MAX_BYTES = 4096
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [7:0]  m_axis_data,
    output logic        m_axis_last,
    output logic        st_valid,
    output logic        st_hdr_ok,
    output logic        st_crc_ok,
    output logic        st_trunc,
    output logic [15:0] st_frame,
    output logic [7:0]  st_idx,
    output logic [3:0]  st_flags,
    output logic [15:0] st_len
);
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

  typedef enum logic [2:0] {S_HDR, S_PAY, S_CRC, S_SKIP, S_INJ} state_t;
  state_t state;

  logic [7:0]  hb[8];             // header bytes
  logic [3:0]  hcnt;
  logic [15:0] pcnt;
  logic [1:0]  ccnt;
  logic [23:0] crc_rx;
  logic        trunc_pending;     // an injected terminator is being sent, status follows

  wire [15:0] len_hdr = {hb[5], hb[4]};

  // payload through the CRC-32 engine; the engine is reset at the end of every input frame
  logic        c_v, c_r, c_l;
  logic [7:0]  c_d;
  logic [31:0] crc_value;
  logic        crc_valid, crc_ok;
  wire         pay_last   = (pcnt == len_hdr - 16'd1);
  wire         in_pay     = (state == S_PAY);
  wire         frame_end  = s_axis_valid & s_axis_ready & s_axis_last;
  crc_engine #(.DW(8)) u_crc (
      .clk(clk), .rst_n(rst_n & ~frame_end),
      .s_axis_valid(s_axis_valid & in_pay), .s_axis_ready(c_r), .s_axis_data(s_axis_data), .s_axis_last(pay_last),
      .m_axis_valid(c_v), .m_axis_ready(m_axis_ready & in_pay), .m_axis_data(c_d), .m_axis_last(c_l),
      .crc_value(crc_value), .crc_valid(crc_valid), .crc_ok(crc_ok));

  wire inj = (state == S_INJ);
  assign m_axis_valid = inj ? 1'b1 : c_v;
  assign m_axis_data  = inj ? 8'h00 : c_d;
  assign m_axis_last  = inj ? 1'b1 : (c_v & pay_last);
  assign s_axis_ready = inj ? 1'b0 : in_pay ? (m_axis_ready & c_r) : 1'b1;
  wire xfer = s_axis_valid & s_axis_ready;

  // status helper tasks are written inline below
  logic [47:0] hdr_flat;
  always_comb begin
    hdr_flat = {hb[5], hb[4], hb[3], hb[2], hb[1], hb[0]};
  end
  wire [15:0] hcrc_calc = crc16_6(hdr_flat);
  wire        hcrc_good = (hcrc_calc == {hb[6], s_axis_data});     // evaluated when byte 7 arrives
  wire        len_fits  = (len_hdr <= 16'(MAX_BYTES));

  wire [31:0] crc_rx_full = {s_axis_data, crc_rx};
  wire [31:0] crc_expect  = (len_hdr == 16'd0) ? 32'd0 : crc_value;

  task automatic emit(input logic hok, input logic cok, input logic tr);
    begin
      st_valid  <= 1'b1;
      st_hdr_ok <= hok;
      st_crc_ok <= cok;
      st_trunc  <= tr;
      st_frame  <= {hb[2], hb[1]};
      st_idx    <= hb[3];
      st_flags  <= hb[0][3:0];
      st_len    <= len_hdr;
    end
  endtask

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state <= S_HDR;
      hcnt  <= '0;
      pcnt  <= '0;
      ccnt  <= '0;
      st_valid <= 1'b0;
      trunc_pending <= 1'b0;
    end else begin
      st_valid <= 1'b0;
      case (state)
        S_HDR: if (xfer) begin
          hb[hcnt[2:0]] <= s_axis_data;
          if (hcnt == 4'd7) begin
            if (hcrc_good && len_fits) begin
              hcnt <= '0;
              pcnt <= '0;
              ccnt <= '0;
              if (s_axis_last) begin
                emit(1'b1, 1'b0, 1'b1);
              end else begin
                state <= (len_hdr == 16'd0) ? S_CRC : S_PAY;
              end
            end else begin
              hb[7] <= s_axis_data;
              // header bad: report now, skip the rest of the frame
              st_valid <= 1'b1; st_hdr_ok <= 1'b0; st_crc_ok <= 1'b0; st_trunc <= 1'b0;
              st_frame <= {hb[2], hb[1]}; st_idx <= hb[3]; st_flags <= hb[0][3:0]; st_len <= len_hdr;
              hcnt  <= '0;
              state <= s_axis_last ? S_HDR : S_SKIP;
            end
          end else if (s_axis_last) begin
            st_valid <= 1'b1; st_hdr_ok <= 1'b0; st_crc_ok <= 1'b0; st_trunc <= 1'b1;
            st_frame <= '0; st_idx <= '0; st_flags <= '0; st_len <= '0;
            hcnt <= '0;
          end else begin
            hcnt <= hcnt + 4'd1;
          end
        end
        S_PAY: if (xfer) begin
          pcnt <= pcnt + 16'd1;
          if (pay_last) begin
            ccnt <= '0;
            if (s_axis_last) begin
              emit(1'b1, 1'b0, 1'b1);
              state <= S_HDR; hcnt <= '0;
            end else begin
              state <= S_CRC;
            end
          end else if (s_axis_last) begin
            state <= S_INJ;          // payload cut short: close the output stream with a dummy last byte
            trunc_pending <= 1'b1;
          end
        end
        S_CRC: if (xfer) begin
          if (ccnt == 2'd3) begin
            emit(1'b1, (crc_rx_full == crc_expect), 1'b0);
            if (s_axis_last) begin state <= S_HDR; hcnt <= '0; end
            else state <= S_SKIP;
            ccnt <= '0;
          end else begin
            case (ccnt)
              2'd0: crc_rx[7:0]   <= s_axis_data;
              2'd1: crc_rx[15:8]  <= s_axis_data;
              default: crc_rx[23:16] <= s_axis_data;
            endcase
            ccnt <= ccnt + 2'd1;
            if (s_axis_last) begin
              emit(1'b1, 1'b0, 1'b1);
              state <= S_HDR; hcnt <= '0;
            end
          end
        end
        S_SKIP: if (xfer && s_axis_last) begin
          state <= S_HDR;
          hcnt  <= '0;
        end
        default: begin      // S_INJ
          if (m_axis_ready) begin
            emit(1'b1, 1'b0, 1'b1);
            trunc_pending <= 1'b0;
            state <= S_HDR;
            hcnt  <= '0;
          end
        end
      endcase
    end
  end

  wire unused_ok = &{1'b0, crc_valid, crc_ok, c_l, trunc_pending};
endmodule
