// tlm_framer - finds frame boundaries in a UART byte stream (design/08-telemetry-bridge.md section 2.3).
module tlm_framer (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] div,
    input  logic [1:0]  proto,
    input  logic [7:0]  idle_bits,
    input  logic [8:0]  max_len,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [7:0]  m_axis_data,
    output logic        m_axis_last,
    output logic        m_axis_err,
    output logic        drop
);
  localparam logic [2:0] F_RAW = 3'd0, F_MAV1 = 3'd1, F_MAV2 = 3'd2, F_MSP = 3'd3, F_MSP1 = 3'd4, F_MSP2 = 3'd5;

  // ---- output register ----
  logic       o_v, o_l, o_e;
  logic [7:0] o_d;
  assign m_axis_valid = o_v;
  assign m_axis_data  = o_d;
  assign m_axis_last  = o_l;
  assign m_axis_err   = o_e;
  wire can_push = ~o_v | m_axis_ready;

  // ---- frame state ----
  logic        in_frame;
  logic [2:0]  fproto;
  logic [9:0]  cnt;          // bytes of the current frame accepted so far
  logic [16:0] total;
  logic        have_total;
  logic [7:0]  lenreg;
  logic        h_v;          // raw mode hold-back register
  logic [7:0]  h_d;

  // ---- idle timer ----
  logic [15:0] tcnt;
  logic [7:0]  idle_cnt;
  wire  [7:0]  idle_lim = (idle_bits == 8'd0) ? 8'd1 : idle_bits;
  wire         timeout  = (idle_cnt >= idle_lim);
  wire  [9:0]  max_l    = {1'b0, max_len};

  wire raw_full = in_frame && (fproto == F_RAW) && h_v && (max_l != 10'd0) && (cnt >= max_l);
  wire flush_to = in_frame && timeout;
  wire flush    = raw_full | flush_to;

  assign s_axis_ready = can_push & ~flush;
  wire take = s_axis_valid & s_axis_ready;

  // ---- combinational decode of the byte for a protocol frame in progress ----
  logic [16:0] tot_n;
  logic [2:0]  fp_n;
  logic        abort_n, set_have, set_len, last_n;

  always_comb begin
    tot_n    = total;
    fp_n     = fproto;
    abort_n  = 1'b0;
    set_have = 1'b0;
    set_len  = 1'b0;
    case (fproto)
      F_MAV1: if (cnt == 10'd1) begin
        tot_n = {9'd0, s_axis_data} + 17'd8;
        set_have = 1'b1;
      end
      F_MAV2: begin
        if (cnt == 10'd1) set_len = 1'b1;
        if (cnt == 10'd2) begin
          tot_n = {9'd0, lenreg} + 17'd12 + (s_axis_data[0] ? 17'd13 : 17'd0);
          set_have = 1'b1;
        end
      end
      F_MSP: if (cnt == 10'd1) begin
        if (s_axis_data == 8'h4D) fp_n = F_MSP1;
        else if (s_axis_data == 8'h58) fp_n = F_MSP2;
        else abort_n = 1'b1;
      end
      F_MSP1: begin
        if (cnt == 10'd2 && !(s_axis_data == 8'h3C || s_axis_data == 8'h3E || s_axis_data == 8'h21)) abort_n = 1'b1;
        if (cnt == 10'd3) begin
          tot_n = {9'd0, s_axis_data} + 17'd6;
          set_have = 1'b1;
        end
      end
      F_MSP2: begin
        if (cnt == 10'd2 && !(s_axis_data == 8'h3C || s_axis_data == 8'h3E || s_axis_data == 8'h21)) abort_n = 1'b1;
        if (cnt == 10'd6) set_len = 1'b1;
        if (cnt == 10'd7) begin
          tot_n = {1'b0, s_axis_data, lenreg} + 17'd9;
          set_have = 1'b1;
        end
      end
      default: ;
    endcase
    if (set_have && (tot_n > {7'd0, max_l})) abort_n = 1'b1;
    last_n = abort_n | ((have_total | set_have) && ({7'd0, cnt} == tot_n - 17'd1));
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      o_v        <= 1'b0;
      in_frame   <= 1'b0;
      fproto     <= F_RAW;
      cnt        <= '0;
      total      <= '0;
      have_total <= 1'b0;
      lenreg     <= '0;
      h_v        <= 1'b0;
      tcnt       <= '0;
      idle_cnt   <= 8'd255;
      drop       <= 1'b0;
    end else begin
      drop <= 1'b0;
      if (o_v && m_axis_ready) o_v <= 1'b0;

      // idle timer: restarts on every accepted byte, counts bit times, saturates
      if (take) begin
        tcnt     <= '0;
        idle_cnt <= 8'd0;
      end else if (tcnt >= div - 16'd1) begin
        tcnt <= '0;
        if (idle_cnt != 8'd255) idle_cnt <= idle_cnt + 8'd1;
      end else begin
        tcnt <= tcnt + 16'd1;
      end

      if (flush && can_push) begin
        // end of a raw frame, or truncated protocol frame
        o_v <= 1'b1;
        o_l <= 1'b1;
        if (fproto == F_RAW) begin
          o_d <= h_d;
          o_e <= 1'b0;
        end else begin
          o_d <= 8'h00;
          o_e <= 1'b1;
        end
        h_v        <= 1'b0;
        in_frame   <= 1'b0;
        have_total <= 1'b0;
      end else if (take) begin
        if (!in_frame) begin
          // ---- look for a start byte ----
          if (proto == 2'd0) begin
            h_v <= 1'b1; h_d <= s_axis_data; in_frame <= 1'b1; fproto <= F_RAW; cnt <= 10'd1;
          end else if ((proto == 2'd1 || proto == 2'd3) && (s_axis_data == 8'hFE || s_axis_data == 8'hFD)) begin
            o_v <= 1'b1; o_d <= s_axis_data; o_l <= 1'b0; o_e <= 1'b0;
            in_frame <= 1'b1; fproto <= (s_axis_data == 8'hFE) ? F_MAV1 : F_MAV2; cnt <= 10'd1; have_total <= 1'b0;
          end else if ((proto == 2'd2 || proto == 2'd3) && s_axis_data == 8'h24) begin
            o_v <= 1'b1; o_d <= s_axis_data; o_l <= 1'b0; o_e <= 1'b0;
            in_frame <= 1'b1; fproto <= F_MSP; cnt <= 10'd1; have_total <= 1'b0;
          end else if (proto == 2'd3) begin
            h_v <= 1'b1; h_d <= s_axis_data; in_frame <= 1'b1; fproto <= F_RAW; cnt <= 10'd1;
          end else begin
            drop <= 1'b1;
          end
        end else if (fproto == F_RAW) begin
          // push the held byte, hold the new one
          o_v <= 1'b1; o_d <= h_d; o_l <= 1'b0; o_e <= 1'b0;
          h_d <= s_axis_data;
          cnt <= cnt + 10'd1;
        end else begin
          // ---- protocol frame: forward the byte, track length and end ----
          o_v    <= 1'b1;
          o_d    <= s_axis_data;
          o_l    <= last_n;
          o_e    <= abort_n;
          total  <= tot_n;
          fproto <= fp_n;
          cnt    <= cnt + 10'd1;
          if (set_len) lenreg <= s_axis_data;
          if (set_have) have_total <= 1'b1;
          if (last_n) begin
            in_frame   <= 1'b0;
            have_total <= 1'b0;
          end
        end
      end
    end
  end
endmodule
