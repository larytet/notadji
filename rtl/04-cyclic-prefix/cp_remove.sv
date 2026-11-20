// cp_remove - cyclic-prefix removal with optional window back-off (design/04-cyclic-prefix.md section 4).
module cp_remove #(
    parameter int W        = 32,
    parameter int MAX_LOG2 = 9
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic [3:0]            fft_log2,
    input  logic [1:0]            cp_sel,
    input  logic [MAX_LOG2-2:0]   backoff,
    input  logic                  s_axis_valid,
    output logic                  s_axis_ready,
    input  logic [W-1:0]          s_axis_data,
    input  logic                  s_axis_last,
    output logic                  m_axis_valid,
    input  logic                  m_axis_ready,
    output logic [W-1:0]          m_axis_data,
    output logic                  m_axis_last,
    output logic                  err_len
);
  localparam int CW = MAX_LOG2 + 2;
  localparam int BW = MAX_LOG2 - 1;

  function automatic [3:0] clamp_log2(input [3:0] v);
    begin
      if (v < 4'd6) clamp_log2 = 4'd6;
      else if (v > 4'(MAX_LOG2)) clamp_log2 = 4'(MAX_LOG2);
      else clamp_log2 = v;
    end
  endfunction

  function automatic [2:0] shift_of(input [1:0] sel);
    begin
      shift_of = (sel == 2'd0) ? 3'd4 : (sel == 2'd1) ? 3'd3 : 3'd2;
    end
  endfunction

  logic [CW-1:0] cnt;
  logic [3:0]    lat_log2;
  logic [2:0]    lat_sh;
  logic [BW-1:0] lat_back;

  wire first = (cnt == '0);
  wire [3:0]    e_log2 = first ? clamp_log2(fft_log2) : lat_log2;
  wire [2:0]    e_sh   = first ? shift_of(cp_sel) : lat_sh;
  wire [BW-1:0] e_back = first ? backoff : lat_back;

  wire [CW-1:0] n       = CW'(1) << e_log2;
  wire [CW-1:0] l       = n >> e_sh;
  wire [CW-1:0] back    = (CW'(e_back) > l) ? l : CW'(e_back);
  wire [CW-1:0] win_lo  = l - back;
  wire [CW-1:0] win_hi  = win_lo + n;      // exclusive
  wire [CW-1:0] total   = n + l;
  wire          in_win  = (cnt >= win_lo) && (cnt < win_hi);
  wire          sym_end = (cnt == total - 1'b1);

  assign m_axis_valid = s_axis_valid & in_win;
  assign s_axis_ready = in_win ? m_axis_ready : 1'b1;
  assign m_axis_data  = s_axis_data;
  assign m_axis_last  = (cnt == win_hi - 1'b1);

  wire xfer = s_axis_valid & s_axis_ready;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      cnt     <= '0;
      err_len <= 1'b0;
    end else begin
      err_len <= 1'b0;
      if (xfer) begin
        if (first) begin
          lat_log2 <= e_log2;
          lat_sh   <= e_sh;
          lat_back <= e_back;
        end
        if (s_axis_last != sym_end) err_len <= 1'b1;
        cnt <= sym_end ? '0 : cnt + 1'b1;
      end
    end
  end
endmodule
