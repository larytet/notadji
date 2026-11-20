// cordic_vec - sequential vectoring CORDIC: angle of (x, y) as a 16-bit phase, 65536 = 2 pi (design/18-sync.md section 1).
module cordic_vec (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               start,
    input  logic signed [23:0] x,
    input  logic signed [23:0] y,
    output logic               busy,
    output logic               done,      // one-clock pulse, angle valid
    output logic [15:0]        angle
);
  // atan(2^-i) / (2 pi) in units of 2^-20 turn
  function automatic [19:0] atan_tab(input [4:0] i);
    begin
      case (i)
        5'd0: atan_tab = 20'd131072;
        5'd1: atan_tab = 20'd77376;
        5'd2: atan_tab = 20'd40884;
        5'd3: atan_tab = 20'd20753;
        5'd4: atan_tab = 20'd10417;
        5'd5: atan_tab = 20'd5213;
        5'd6: atan_tab = 20'd2607;
        5'd7: atan_tab = 20'd1304;
        5'd8: atan_tab = 20'd652;
        5'd9: atan_tab = 20'd326;
        5'd10: atan_tab = 20'd163;
        5'd11: atan_tab = 20'd81;
        5'd12: atan_tab = 20'd41;
        5'd13: atan_tab = 20'd20;
        5'd14: atan_tab = 20'd10;
        default: atan_tab = 20'd5;
      endcase
    end
  endfunction

  logic signed [25:0] xr, yr;
  logic        [19:0] zr;
  logic        [4:0]  it;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      busy <= 1'b0;
      done <= 1'b0;
    end else begin
      done <= 1'b0;
      if (start && !busy) begin
        // pre-rotation into the right half plane (half a turn is 2^19 in this unit)
        if (x < 0) begin
          xr <= -{{2{x[23]}}, x};
          yr <= -{{2{y[23]}}, y};
          zr <= 20'd524288;
        end else begin
          xr <= {{2{x[23]}}, x};
          yr <= {{2{y[23]}}, y};
          zr <= 20'd0;
        end
        it   <= 5'd0;
        busy <= 1'b1;
      end else if (busy) begin
        if (it == 5'd16) begin
          angle <= 16'((zr + 20'd8) >> 4);
          done  <= 1'b1;
          busy  <= 1'b0;
        end else begin
          if (yr >= 0) begin
            xr <= xr + (yr >>> it);
            yr <= yr - (xr >>> it);
            zr <= zr + atan_tab(it);
          end else begin
            xr <= xr - (yr >>> it);
            yr <= yr + (xr >>> it);
            zr <= zr - atan_tab(it);
          end
          it <= it + 5'd1;
        end
      end
    end
  end
endmodule
