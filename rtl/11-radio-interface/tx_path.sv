// tx_path - modem samples to the radio clock; zero fill and counting on underrun (design/11-radio-interface.md section 2).
module tx_path #(
    parameter int AW = 4
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [31:0] s_axis_data,
    input  logic        tx_run,
    input  logic        tx_clk,
    input  logic        tx_rst_n,
    input  logic        tx_req,
    output logic [31:0] tx_data,
    output logic        tx_valid,
    output logic [15:0] tx_underrun_cnt
);
  logic run1, run2;
  always_ff @(posedge tx_clk) begin
    if (!tx_rst_n) begin
      run1 <= 1'b0;
      run2 <= 1'b0;
    end else begin
      run1 <= tx_run;
      run2 <= run1;
    end
  end

  logic        f_valid, f_last;
  logic [31:0] f_data;
  wire         take = tx_req & run2;
  axis_cdc_fifo #(.W(32), .AW(AW)) u_fifo (
      .s_clk(clk), .s_rst_n(rst_n), .s_axis_valid(s_axis_valid), .s_axis_ready(s_axis_ready), .s_axis_data(s_axis_data), .s_axis_last(1'b0),
      .m_clk(tx_clk), .m_rst_n(tx_rst_n), .m_axis_valid(f_valid), .m_axis_ready(take), .m_axis_data(f_data), .m_axis_last(f_last));

  assign tx_valid = take & f_valid;
  assign tx_data  = (take & f_valid) ? f_data : 32'd0;

  gray_cnt_sync u_cnt (
      .src_clk(tx_clk), .src_rst_n(tx_rst_n), .inc(take & ~f_valid),
      .dst_clk(clk), .dst_rst_n(rst_n), .cnt_dst(tx_underrun_cnt));

  wire unused_ok = &{1'b0, f_last};
endmodule
