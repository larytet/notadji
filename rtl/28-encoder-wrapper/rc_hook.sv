// rc_hook - validated rate-control interface to the encoder (design/28-encoder-wrapper.md section 1.5).
module rc_hook (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] max_budget,
    input  logic        budget_valid,
    input  logic [15:0] budget_in,              // bytes per slice, from module 23
    input  logic        qp_valid,
    input  logic [7:0]  qp_bias_in,
    input  logic [7:0]  qp_bias_max,
    output logic [15:0] target_bytes,
    output logic        update,
    output logic [7:0]  qp_bias,
    output logic        qp_update,
    output logic [15:0] err_rc
);
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      target_bytes <= '0;
      update <= 1'b0;
      qp_bias <= '0;
      qp_update <= 1'b0;
      err_rc <= '0;
    end else begin
      update <= 1'b0;
      qp_update <= 1'b0;
      begin
        logic [15:0] e;
        e = err_rc;
        if (budget_valid) begin
          if (budget_in == 16'd0 || budget_in > max_budget) e = e + 16'd1;
          else begin
            target_bytes <= budget_in;
            update <= 1'b1;
          end
        end
        if (qp_valid) begin
          if (qp_bias_in > qp_bias_max) e = e + 16'd1;
          else begin
            qp_bias <= qp_bias_in;
            qp_update <= 1'b1;
          end
        end
        err_rc <= e;
      end
    end
  end
endmodule
