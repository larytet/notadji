// nal_split - Annex-B NAL unit splitter (design/28-encoder-wrapper.md section 1.1).
module nal_split #(
    parameter int CODEC = 0,                    // 0 AVC, 1 HEVC
    parameter int MAX_NAL = 65535
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        flush,                  // closes the NAL unit in progress (end of stream)
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [7:0]  s_data,
    output logic        m_valid,
    input  logic        m_ready,
    output logic [7:0]  m_data,
    output logic        m_last,
    output logic [5:0]  nal_type,               // valid with the first byte of a NAL unit
    output logic        is_slice,
    output logic        is_idr,
    output logic [15:0] err_overflow
);
  logic [7:0] zc;                               // zero bytes seen (pending)
  logic       in_nal;
  logic       first_app;                        // the next appended byte is the NAL header
  logic       hold_v;
  logic [7:0] hold_d;
  logic [8:0] app_cnt;                          // pending appends: zeros, then pend_b
  logic       app_has_b;
  logic [7:0] pend_b;
  logic [16:0] nbytes;
  logic       ovf_flag;

  wire out_free = !m_valid || m_ready;
  assign s_ready = out_free && (app_cnt == 9'd0);

  /* verilator lint_off UNUSED */
  function automatic logic [5:0] ntype(input logic [7:0] b);
    ntype = (CODEC == 0) ? {1'b0, b[4:0]} : b[6:1];
  endfunction
  /* verilator lint_on UNUSED */
  function automatic logic isslice(input logic [5:0] t);
    isslice = (CODEC == 0) ? (t == 6'd1 || t == 6'd5) : (t <= 6'd9 || (t >= 6'd16 && t <= 6'd21));
  endfunction
  function automatic logic isidr(input logic [5:0] t);
    isidr = (CODEC == 0) ? (t == 6'd5) : (t == 6'd19 || t == 6'd20);
  endfunction

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      zc <= '0;
      in_nal <= 1'b0;
      first_app <= 1'b0;
      hold_v <= 1'b0;
      hold_d <= '0;
      app_cnt <= '0;
      app_has_b <= 1'b0;
      pend_b <= '0;
      nbytes <= '0;
      ovf_flag <= 1'b0;
      m_valid <= 1'b0;
      m_data <= '0;
      m_last <= 1'b0;
      nal_type <= '0;
      is_slice <= 1'b0;
      is_idr <= 1'b0;
      err_overflow <= '0;
    end else begin
      if (m_valid && m_ready) m_valid <= 1'b0;
      if (app_cnt != 9'd0) begin
        // append one byte (a pending zero, then the byte that ended the zero run)
        if (out_free) begin
          /* verilator lint_off UNUSED */
          logic [7:0] b;
          /* verilator lint_on UNUSED */
          b = (app_has_b && app_cnt == 9'd1) ? pend_b : 8'd0;
          app_cnt <= app_cnt - 9'd1;
          if (first_app) begin
            first_app <= 1'b0;
            nal_type <= ntype(b);
            is_slice <= isslice(ntype(b));
            is_idr <= isidr(ntype(b));
          end
          nbytes <= nbytes + 17'd1;
          if (nbytes >= 17'(MAX_NAL)) begin
            if (!ovf_flag) begin
              ovf_flag <= 1'b1;
              err_overflow <= err_overflow + 16'd1;
            end
          end else begin
            if (hold_v) begin
              m_valid <= 1'b1;
              m_data <= hold_d;
              m_last <= 1'b0;
            end
            hold_v <= 1'b1;
            hold_d <= b;
          end
        end
      end else if (s_valid && out_free) begin
        if (s_data == 8'd0) begin
          if (zc != 8'd255) zc <= zc + 8'd1;
        end else if (s_data == 8'd1 && zc >= 8'd2) begin
          // start code: close the NAL unit in progress
          if (hold_v) begin
            m_valid <= 1'b1;
            m_data <= hold_d;
            m_last <= 1'b1;
            hold_v <= 1'b0;
          end
          in_nal <= 1'b1;
          first_app <= 1'b1;
          nbytes <= '0;
          ovf_flag <= 1'b0;
          zc <= '0;
          app_cnt <= '0;
        end else begin
          if (in_nal) begin
            app_cnt <= {1'b0, zc} + 9'd1;
            app_has_b <= 1'b1;
            pend_b <= s_data;
          end
          zc <= '0;
        end
      end else if (flush && out_free && app_cnt == 9'd0) begin
        if (hold_v) begin
          m_valid <= 1'b1;
          m_data <= hold_d;
          m_last <= 1'b1;
          hold_v <= 1'b0;
        end
        in_nal <= 1'b0;
        zc <= '0;
      end
    end
  end
endmodule
