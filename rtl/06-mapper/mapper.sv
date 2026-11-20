// mapper - Gray-labelled BPSK/QPSK/16QAM/64QAM/256QAM, RMS 4096 (design/06-constellation-mapper.md).
// Zero-latency pass-through: valid/ready are combinational; mod is sampled with every beat.
module mapper (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [2:0]  mod,
    input  logic        s_axis_valid,
    output logic        s_axis_ready,
    input  logic [7:0]  s_axis_data,
    input  logic        s_axis_last,
    output logic        m_axis_valid,
    input  logic        m_axis_ready,
    output logic [31:0] m_axis_data,
    output logic        m_axis_last
);
  // magnitude of the odd PAM levels 1,3,5,... for each number of bits per axis (m = 1..4)
  function automatic [12:0] mag(input [2:0] m, input [2:0] j);
    begin
      case (m)
        3'd1: mag = 13'd2896;
        3'd2: mag = (j == 3'd0) ? 13'd1295 : 13'd3886;
        3'd3: begin
          case (j[1:0])
            2'd0: mag = 13'd632;
            2'd1: mag = 13'd1896;
            2'd2: mag = 13'd3160;
            default: mag = 13'd4424;
          endcase
        end
        default: begin
          case (j)
            3'd0: mag = 13'd314;
            3'd1: mag = 13'd942;
            3'd2: mag = 13'd1571;
            3'd3: mag = 13'd2199;
            3'd4: mag = 13'd2827;
            3'd5: mag = 13'd3456;
            3'd6: mag = 13'd4084;
            default: mag = 13'd4712;
          endcase
        end
      endcase
    end
  endfunction

  // one axis: g = m Gray bits with the first bit in time in bit 0 (the most significant Gray bit)
  function automatic [15:0] axis(input [2:0] m, input [3:0] g);
    reg [3:0] gm;     // Gray code, most significant bit first
    reg [3:0] b;      // binary
    reg [2:0] j;
    reg       pos;
    reg [12:0] a;
    integer i;
    integer mi;
    begin
      mi = {29'd0, m};
      gm = 4'd0;
      for (i = 0; i < 4; i = i + 1) begin
        if (i < mi) gm[mi-1-i] = g[i];
      end
      b = 4'd0;
      b[mi-1] = gm[mi-1];
      for (i = 2; i <= 4; i = i + 1) begin
        if (i <= mi) b[mi-i] = b[mi-i+1] ^ gm[mi-i];
      end
      // level = 2b - (2^m - 1); sign from the top bit, index of the magnitude
      pos = b[mi-1];
      if (pos) j = 3'(b - (4'd1 << (mi - 1)));
      else     j = 3'(((4'd1 << (mi - 1)) - 4'd1) - b);
      a = mag(m, j);
      axis = pos ? {3'b000, a} : (~{3'b000, a} + 16'd1);
    end
  endfunction

  logic [2:0]  m_ax;
  logic        bpsk;
  logic [15:0] i_val, q_val;

  always_comb begin
    bpsk = 1'b0;
    case (mod)
      3'd1:    m_ax = 3'd1;
      3'd2:    m_ax = 3'd2;
      3'd3:    m_ax = 3'd3;
      3'd4:    m_ax = 3'd4;
      default: begin m_ax = 3'd1; bpsk = 1'b1; end
    endcase
    if (bpsk) begin
      i_val = s_axis_data[0] ? 16'd4096 : 16'hF000;   // bit 0 = 1 gives +4096, 0 gives -4096
      q_val = 16'd0;
    end else begin
      i_val = axis(m_ax, s_axis_data[3:0]);
      q_val = axis(m_ax, 4'(s_axis_data[7:0] >> m_ax));
    end
  end

  assign m_axis_valid = s_axis_valid;
  assign s_axis_ready = m_axis_ready;
  assign m_axis_data  = {q_val, i_val};
  assign m_axis_last  = s_axis_last;

  wire unused_ok = &{1'b0, clk, rst_n};
endmodule
