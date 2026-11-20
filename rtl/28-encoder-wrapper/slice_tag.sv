// slice_tag - frame and slice numbering, flags, routing of non-slice NAL units (design/28-encoder-wrapper.md section 1.2).
module slice_tag #(
    parameter int CODEC = 0
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        frame_src,              // 0: delimiter NAL, 1: frame_sync pulse
    input  logic        frame_sync,
    input  logic [7:0]  slices_per_frame,
    input  logic [63:0] tag_mask,               // intra commanded for the frame now leaving the encoder
    // NAL stream in
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [7:0]  s_data,
    input  logic        s_last,
    input  logic [5:0]  nal_type,
    input  logic        is_slice,
    input  logic        is_idr,
    // slice stream out (to slice_pack), sideband valid with the first byte
    output logic        m_valid,
    input  logic        m_ready,
    output logic [7:0]  m_data,
    output logic        m_last,
    output logic [15:0] meta_frame,
    output logic [7:0]  meta_idx,
    output logic [3:0]  meta_flags,
    // parameter sets, SEI, delimiters
    output logic        ps_valid,
    input  logic        ps_ready,
    output logic [7:0]  ps_data,
    output logic        ps_last,
    // frame boundary marker
    output logic        bs_start,
    output logic [15:0] bs_frame,
    output logic [15:0] err_count
);
  logic        first;                           // the next byte is the first of a NAL unit
  logic        cur_slice;                       // the NAL unit in progress is a slice
  logic [15:0] frame;
  logic [7:0]  cnt;
  logic [63:0] mask_l;
  logic [15:0] t_frame;
  logic [7:0]  t_idx;
  logic [3:0]  t_flags;

  wire aud = (CODEC == 0) ? (nal_type == 6'd9) : (nal_type == 6'd35);
  wire this_slice = first ? is_slice : cur_slice;
  wire [7:0] idx_now = cnt;
  wire [3:0] flags_now = {2'b00, (idx_now + 8'd1 == slices_per_frame), (mask_l[idx_now[5:0]] | is_idr)};

  assign m_valid = s_valid & this_slice;
  assign m_data = s_data;
  assign m_last = s_last;
  assign ps_valid = s_valid & ~this_slice;
  assign ps_data = s_data;
  assign ps_last = s_last;
  assign s_ready = this_slice ? m_ready : ps_ready;
  assign meta_frame = first ? frame : t_frame;
  assign meta_idx = first ? idx_now : t_idx;
  assign meta_flags = first ? flags_now : t_flags;
  assign bs_frame = frame;

  wire xfer = s_valid && s_ready;
  wire boundary_aud = xfer && first && !frame_src && aud;
  wire boundary_sync = frame_src && frame_sync;
  wire boundary = boundary_aud || boundary_sync;
  assign bs_start = boundary;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      first <= 1'b1;
      cur_slice <= 1'b0;
      frame <= 16'hFFFF;
      cnt <= '0;
      mask_l <= '0;
      t_frame <= '0;
      t_idx <= '0;
      t_flags <= '0;
      err_count <= '0;
    end else begin
      if (boundary) begin
        if (cnt != 8'd0 && cnt != slices_per_frame) err_count <= err_count + 16'd1;
        frame <= frame + 16'd1;
        cnt <= '0;
        mask_l <= tag_mask;
      end
      if (xfer) begin
        if (first) begin
          cur_slice <= is_slice;
          if (is_slice) begin
            t_frame <= frame;
            t_idx <= idx_now;
            t_flags <= flags_now;
            if (idx_now >= slices_per_frame) err_count <= err_count + 16'd1;
            cnt <= boundary ? 8'd1 : cnt + 8'd1;
          end
        end
        first <= s_last;
      end
    end
  end
endmodule
