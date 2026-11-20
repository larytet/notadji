// scan_engine - channel pointer, scan slots and result table (design/24-spectrum-scan.md section 1.2).
module scan_engine (
    input  logic        clk,
    input  logic        rst_n,
    // configuration
    input  logic [31:0] ch_mask,
    input  logic [5:0]  n_ch,
    input  logic [15:0] settle_ticks,
    input  logic [16:0] dwell_ticks,
    input  logic [47:0] strong_thr,
    input  logic [4:0]  home,
    input  logic [23:0] tmo_ticks,            // clocks to wait for rx_ready (0: wait for ever)
    input  logic        clear,
    // control
    input  logic        slot,
    input  logic        rx_ready,
    output logic        retune_req,
    output logic [4:0]  retune_ch,
    output logic        back,
    output logic        slot_done,
    output logic        no_ch,
    output logic        result_valid,
    output logic [4:0]  result_ch,
    // samples
    input  logic        s_valid,
    input  logic [31:0] s_data,
    // table read
    input  logic [4:0]  rd_ch,
    output logic [47:0] rd_last,
    output logic [11:0] rd_lg,
    output logic [47:0] rd_max,
    output logic [15:0] rd_count,
    output logic        rd_strong,
    output logic [15:0] scan_cnt,
    output logic        err_tmo,
    output logic        busy,
    output logic [15:0] ovr_cnt
);
  typedef enum logic [1:0] {S_IDLE, S_WAIT, S_MEAS} state_t;
  state_t state;
  logic [4:0]  ptr;
  logic        have_ptr;
  logic [4:0]  cur;
  logic [23:0] wcnt;

  // next enabled channel after ptr
  logic [4:0] nxt;
  logic       found;
  wire  [4:0] base = have_ptr ? ptr : 5'd31;        // the first slot starts the search at channel 0
  always_comb begin
    nxt   = base;
    found = 1'b0;
    for (int k = 1; k <= 32; k++) begin
      logic [4:0] c;
      c = base + 5'(k);
      if (!found && ({1'b0, c} < n_ch) && ch_mask[c] && (c != home)) begin
        nxt   = c;
        found = 1'b1;
      end
    end
  end

  logic        m_start, m_busy, m_done, m_sat;
  logic [47:0] m_sum;
  logic [11:0] m_lg;
  scan_meas u_meas (.clk(clk), .rst_n(rst_n), .start(m_start), .settle_ticks(settle_ticks), .dwell_ticks(dwell_ticks), .s_valid(s_valid),
      .s_data(s_data), .busy(m_busy), .done(m_done), .sum(m_sum), .lg(m_lg), .sat(m_sat), .ovr_cnt(ovr_cnt));

  logic [47:0] t_last [32];
  logic [11:0] t_lg   [32];
  logic [47:0] t_max  [32];
  logic [15:0] t_cnt  [32];
  logic [31:0] t_str;

  assign busy = (state != S_IDLE);
  wire unused_ok = &{1'b0, m_busy, m_sat};

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state        <= S_IDLE;
      ptr          <= 5'd0;
      have_ptr     <= 1'b0;
      cur          <= 5'd0;
      wcnt         <= '0;
      retune_req   <= 1'b0;
      retune_ch    <= '0;
      back         <= 1'b0;
      slot_done    <= 1'b0;
      no_ch        <= 1'b0;
      result_valid <= 1'b0;
      result_ch    <= '0;
      scan_cnt     <= '0;
      err_tmo      <= 1'b0;
      m_start      <= 1'b0;
      t_str        <= '0;
      for (int i = 0; i < 32; i++) begin
        t_last[i] <= '0;
        t_lg[i]   <= '0;
        t_max[i]  <= '0;
        t_cnt[i]  <= '0;
      end
    end else begin
      retune_req   <= 1'b0;
      slot_done    <= 1'b0;
      no_ch        <= 1'b0;
      result_valid <= 1'b0;
      m_start      <= 1'b0;
      if (clear) begin
        err_tmo  <= 1'b0;
        scan_cnt <= '0;
        have_ptr <= 1'b0;
        t_str    <= '0;
        for (int i = 0; i < 32; i++) begin
          t_last[i] <= '0;
          t_lg[i]   <= '0;
          t_max[i]  <= '0;
          t_cnt[i]  <= '0;
        end
      end
      case (state)
        S_IDLE: begin
          if (slot) begin
            if (!found) begin
              slot_done <= 1'b1;
              no_ch     <= 1'b1;
            end else begin
              if (have_ptr && nxt <= ptr) scan_cnt <= scan_cnt + 16'd1;
              ptr        <= nxt;
              have_ptr   <= 1'b1;
              cur        <= nxt;
              retune_req <= 1'b1;
              retune_ch  <= nxt;
              back       <= 1'b0;
              wcnt       <= '0;
              state      <= S_WAIT;
            end
          end
        end
        S_WAIT: begin
          wcnt <= wcnt + 24'd1;
          if (rx_ready) begin
            m_start <= 1'b1;
            state   <= S_MEAS;
          end else if (tmo_ticks != 24'd0 && wcnt >= tmo_ticks) begin
            err_tmo    <= 1'b1;
            retune_req <= 1'b1;
            retune_ch  <= home;
            back       <= 1'b1;
            slot_done  <= 1'b1;
            state      <= S_IDLE;
          end
        end
        default: begin
          if (m_done) begin
            t_last[cur] <= m_sum;
            t_lg[cur]   <= m_lg;
            t_max[cur]  <= (t_cnt[cur] == 16'd0 || m_sum > t_max[cur]) ? m_sum : t_max[cur];
            t_cnt[cur]  <= t_cnt[cur] + 16'd1;
            t_str[cur]  <= (m_sum > strong_thr);
            result_valid <= 1'b1;
            result_ch    <= cur;
            retune_req   <= 1'b1;
            retune_ch    <= home;
            back         <= 1'b1;
            slot_done    <= 1'b1;
            state        <= S_IDLE;
          end
        end
      endcase
    end
  end

  always_ff @(posedge clk) begin
    rd_last   <= t_last[rd_ch];
    rd_lg     <= t_lg[rd_ch];
    rd_max    <= t_max[rd_ch];
    rd_count  <= t_cnt[rd_ch];
    rd_strong <= t_str[rd_ch];
  end
endmodule
