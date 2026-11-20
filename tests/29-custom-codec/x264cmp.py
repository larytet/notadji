"""x264 on the same luma sequence (constant QP, low-latency settings, 8 slices, no B-frames) through ffmpeg."""
import os
import subprocess
import tempfile

import numpy as np


def run_x264(frames, qp, slices=8, preset="medium", extra=""):
    H, W = frames[0].shape
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "in.gray")
        out = os.path.join(d, "out.mp4")
        dec = os.path.join(d, "dec.gray")
        np.stack(frames).astype(np.uint8).tofile(raw)
        params = f"slices={slices}:bframes=0:rc-lookahead=0:sync-lookahead=0:keyint=infinite:scenecut=0{extra}"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}", "-r", "60", "-i", raw,
               "-vf", "scale=in_range=pc:out_range=pc,format=yuv420p", "-color_range", "pc", "-c:v", "libx264", "-preset", preset, "-tune", "zerolatency", "-qp", str(qp), "-x264-params", params, "-f", "mp4", out]
        subprocess.check_call(cmd)
        pk = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=size", "-of", "csv=p=0", out], capture_output=True, text=True).stdout.split()
        size = sum(int(x) for x in pk)             # coded packets only (no container)
        subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", out, "-vf", "scale=in_range=pc:out_range=pc,format=gray", "-f", "rawvideo", dec])
        rec = np.fromfile(dec, dtype=np.uint8).reshape(-1, H, W)
    ps = []
    for a, b in zip(frames, rec):
        mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
        ps.append(99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse))
    return size, float(np.mean(ps))
