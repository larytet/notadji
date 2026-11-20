// axis_width_conv - integer-ratio width converter (design/01-axi-library.md section 3.3).
// Little-endian packing. err_frame pulses for one clock when an up-converted frame ends
// off a word boundary; the partial word is flushed with zero fill.
module axis_width_conv #(
    parameter int IN_W  = 8,
    parameter int OUT_W = 32
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic             s_axis_valid,
    output logic             s_axis_ready,
    input  logic [IN_W-1:0]  s_axis_data,
    input  logic             s_axis_last,
    output logic             m_axis_valid,
    input  logic             m_axis_ready,
    output logic [OUT_W-1:0] m_axis_data,
    output logic             m_axis_last,
    output logic             err_frame
);
  generate
    if (IN_W == OUT_W) begin : g_pass
      assign m_axis_valid = s_axis_valid;
      assign s_axis_ready = m_axis_ready;
      assign m_axis_data  = s_axis_data;
      assign m_axis_last  = s_axis_last;
      assign err_frame    = 1'b0;

    end else if (OUT_W > IN_W) begin : g_up
      localparam int R  = OUT_W / IN_W;
      localparam int CW = (R > 1) ? $clog2(R) : 1;

      logic [OUT_W-1:0] acc, out_d;
      logic [CW-1:0] cnt;
      logic out_v, out_l;

      assign s_axis_ready = ~out_v | m_axis_ready;
      assign m_axis_valid = out_v;
      assign m_axis_data  = out_d;
      assign m_axis_last  = out_l;

      wire in_xfer = s_axis_valid & s_axis_ready;
      wire full_grp = (cnt == CW'(R - 1));
      wire emit = in_xfer & (full_grp | s_axis_last);
      wire [OUT_W-1:0] word_n = acc | (OUT_W'(s_axis_data) << (cnt * IN_W));

      always_ff @(posedge clk) begin
        if (!rst_n) begin
          cnt       <= '0;
          acc       <= '0;
          out_v     <= 1'b0;
          err_frame <= 1'b0;
        end else begin
          err_frame <= 1'b0;
          if (m_axis_ready) out_v <= 1'b0;
          if (in_xfer) begin
            if (emit) begin
              out_v <= 1'b1;
              out_d <= word_n;
              out_l <= s_axis_last;
              acc   <= '0;
              cnt   <= '0;
              if (s_axis_last && !full_grp) err_frame <= 1'b1;
            end else begin
              acc <= word_n;
              cnt <= cnt + 1'b1;
            end
          end
        end
      end

    end else begin : g_down
      localparam int R  = IN_W / OUT_W;
      localparam int CW = (R > 1) ? $clog2(R) : 1;

      logic [IN_W-1:0] hold;
      logic hold_v, hold_l;
      logic [CW-1:0] idx;

      wire last_piece = (idx == CW'(R - 1));
      assign m_axis_valid = hold_v;
      assign m_axis_data  = hold[idx*OUT_W+:OUT_W];
      assign m_axis_last  = hold_l & last_piece;
      assign s_axis_ready = ~hold_v | (m_axis_ready & last_piece);
      assign err_frame    = 1'b0;

      wire in_xfer = s_axis_valid & s_axis_ready;
      wire m_xfer  = hold_v & m_axis_ready;

      always_ff @(posedge clk) begin
        if (!rst_n) begin
          hold_v <= 1'b0;
          idx    <= '0;
        end else begin
          if (m_xfer) begin
            if (last_piece) begin
              hold_v <= 1'b0;
              idx    <= '0;
            end else begin
              idx <= idx + 1'b1;
            end
          end
          if (in_xfer) begin
            hold_v <= 1'b1;
            idx    <= '0;
          end
        end
      end

      always_ff @(posedge clk) begin
        if (in_xfer) begin
          hold   <= s_axis_data;
          hold_l <= s_axis_last;
        end
      end
    end
  endgenerate
endmodule
