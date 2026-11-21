"""Tests of profile SL2 (design/32-codec-efficiency.md section 3). Usage: python3 test_sl2.py [section ...]
Sections: t01 t02 t03 t04 t05 t06 t07 t09 (default: all). Exits non-zero when an assertion fails."""
import math
import random
import sys
from multiprocessing import Pool

import numpy as np

import rd
import sl2
import x264cmp as X

W, H, SH = rd.W, rd.H, rd.SH
ALL = sl2.T_ALL
TOOLS = [("DCT", sl2.T_DCT), ("intra modes", sl2.T_INTRA), ("quarter-pel", sl2.T_SUBPEL), ("context coding", sl2.T_CTX),
         ("deblocking", sl2.T_DEBLOCK), ("RDO", sl2.T_RDO)]


# ---------------------------------------------------------------- T32-01
def t01():
    print("T32-01 transform")
    T = np.array([[64, 64, 64, 64, 64, 64, 64, 64], [89, 75, 50, 18, -18, -50, -75, -89], [83, 36, -36, -83, -83, -36, 36, 83],
                  [75, -18, -89, -50, 50, 89, 18, -75], [64, -64, -64, 64, 64, -64, -64, 64], [50, -89, 18, 75, -75, -18, 89, -50],
                  [36, -83, 83, -36, -36, 83, -83, 36], [18, -50, 75, -89, 89, -75, 50, -18]], dtype=np.int64)
    rng = np.random.default_rng(1)
    worst, n = 0, 0
    blocks = [rng.integers(-255, 256, (8, 8)) for _ in range(1500)]
    blocks += [np.full((8, 8), 255), np.full((8, 8), -255), np.zeros((8, 8), int), rng.choice([-255, 255], (8, 8))]
    for x in blocks:
        x = x.astype(np.int64)
        y = (T @ x + 2) >> 2
        c_ref = (y @ T.T + 256) >> 9
        c = sl2.fwd(x)
        assert (c == c_ref).all(), "C forward DCT differs from the definition"
        z = (T.T @ c_ref + 64) >> 7
        x_ref = (z @ T + 2048) >> 12
        xi = sl2.inv(c_ref)
        assert (xi == x_ref).all(), "C inverse DCT differs from the definition"
        worst = max(worst, int(np.abs(xi - x).max()))
        n += 1
    assert worst <= 2, worst
    # the Hadamard (SL1) path is exact
    for x in blocks[:200]:
        assert (sl2.inv(sl2.fwd(x, False), False) == x).all()
    print(f"  {n} blocks: C forward and inverse DCT equal the integer definition; round trip without quantisation within {worst} level; Hadamard exact")


# ---------------------------------------------------------------- T32-02
def fov_map(strength=10, radius=56, width=40):
    m = np.zeros((rd.H // 16, rd.W // 16), np.int8)
    cx, cy = rd.W / 2, rd.H / 2
    for j in range(m.shape[0]):
        for i in range(m.shape[1]):
            d = math.hypot(i * 16 + 8 - cx, j * 16 + 8 - cy)
            t = min(1.0, max(0.0, (d - radius) / width))
            m[j, i] = int(round(strength * t * t * (3 - 2 * t)))
    return np.ascontiguousarray(m)


def closed_loop(args):
    tools, fov, waves, nf = args
    seq = rd.get_seq(0, nf)
    c = sl2.Codec(W, H, SH, tools)
    dqp = fov_map() if fov else None
    ref_e = ref_d = None
    for k, f in enumerate(seq):
        intra = {k % 8} if waves and k >= 2 else set()
        sl, rec, _ = c.encode_frame(f, ref_e, qp=28, intra=intra, dqp=dqp)
        dec = c.decode_frame(sl, ref_d)
        if not (dec == rec).all():
            return f"frame {k}: {(dec != rec).sum()} pixels differ"
        ref_e = rec
        ref_d = dec
    return "ok"


def t02():
    print("T32-02 closed loop (decoder reconstruction equals the encoder's)")
    jobs = [("all tools", ALL, False, True), ("all tools, foveation", ALL, True, True), ("no tools", 0, False, True)]
    jobs += [(f"all except {n}", ALL & ~b, False, True) for n, b in TOOLS]
    with Pool(12) as p:
        res = p.map(closed_loop, [(t, fv, wv, 12) for _, t, fv, wv in jobs])
    bad = False
    for (name, *_), r in zip(jobs, res):
        print(f"  {name:<28} 12 frames, refresh wave: {r}")
        bad |= r != "ok"
    assert not bad


# ---------------------------------------------------------------- T32-03
def t03():
    print("T32-03 slice independence")
    seq = rd.get_seq(0, 3)
    c = sl2.Codec(W, H, SH, ALL)
    sl0, rec0, _ = c.encode_frame(seq[0], None, qp=28)
    sl1, rec1, _ = c.encode_frame(seq[1], rec0, qp=28)
    full = c.decode_frame(sl1, rec0)
    assert (full == rec1).all()
    rng = random.Random(5)
    subsets = [[i] for i in range(8)] + [[0, 2, 4, 6], [1, 3, 5, 7], [0, 1, 2, 3], list(range(8)), []]
    subsets += [sorted(rng.sample(range(8), rng.randint(1, 7))) for _ in range(8)]
    n_ok = 0
    for sub in subsets:
        part = c.decode_frame([sl1[i] if i in sub else None for i in range(8)], rec0)
        for i in range(8):
            rows = slice(i * SH, (i + 1) * SH)
            exp = full[rows] if i in sub else rec0[rows]
            assert (part[rows] == exp).all(), f"subset {sub}: slice {i}"
        n_ok += len(sub)
    # corruption of one slice leaves the others unchanged
    for k in range(8):
        bad = bytearray(sl1[k])
        for j in range(1, min(len(bad), 40)):
            bad[j] ^= 0x5A
        sls = list(sl1)
        sls[k] = bytes(bad)
        out = c.decode_frame(sls, rec0)
        for i in range(8):
            if i != k:
                rows = slice(i * SH, (i + 1) * SH)
                assert (out[rows] == full[rows]).all(), f"corrupted slice {k} changed slice {i}"
    print(f"  {len(subsets)} subsets ({n_ok} decoded slices) equal the full decode, missing slices equal the previous frame; corrupting any one of 8 slices leaves the other 7 untouched")


# ---------------------------------------------------------------- T32-04
def t04():
    print("T32-04 rate bound")
    seq = rd.get_seq(0, 4)
    c = sl2.Codec(W, H, SH, ALL)
    ref = None
    for f in seq[:3]:
        _, ref, _ = c.encode_frame(f, ref, qp=32)
    out_lines = []
    allskip = []
    src = np.ascontiguousarray(seq[3])
    rec = np.zeros_like(src)
    for s in range(8):
        b, q, ne = c.enc_slice_budget(src, ref, rec, s, False, 1)
        allskip.append(len(b))
    print(f"  all-skip (zero coefficient) size of the P slices: {min(allskip)} to {max(allskip)} bytes")
    for intra in (False, True):
        mins = []
        for budget in (150, 300, 600, 1200, 2400, 6000):
            ratios, ncs, ps = [], [], []
            _, r2, info = None, None, None
            sls, recon, info = c.encode_frame(seq[3], None if intra else ref, budgets=budget)
            for s, (b, (q, ne)) in enumerate(zip(sls, info)):
                lim = (min(allskip) if not intra else 0)
                ratios.append(len(b) / budget)
                ncs.append(ne)
                if budget >= max(allskip) + 8 and not intra:
                    assert len(b) <= 1.05 * budget, f"slice {s} budget {budget}: {len(b)}"
            out_lines.append(f"  {'intra' if intra else 'P    '} frame, budget {budget:5d} B per slice: size/budget max {max(ratios):.2f} mean {np.mean(ratios):.2f}, QP mean {np.mean([q for q, _ in info]):.1f}, encodes per slice mean {np.mean(ncs):.1f}, PSNR {rd.psnr(seq[3], recon):.1f} dB")
    print("\n".join(out_lines))


# ---------------------------------------------------------------- T32-05
QPS = [14, 18, 22, 26, 30, 34, 38, 42, 46]


def curve(tools):
    with Pool(12) as p:
        res = p.map(rd.run_sl2, [(tools, q, 0, rd.NF) for q in QPS])
    return [(b, ps) for b, ps, _ in res]


def t05():
    print("T32-05 rate and distortion against x264, ablation")
    seq = rd.get_seq(0, rd.NF)
    xc = []
    for q in (20, 24, 28, 32, 36, 40, 44):
        sz, ps = X.run_x264([f.astype(np.int64) for f in seq], q)
        xc.append((sz * 8 / rd.NF / rd.BPP, ps))
    print("  x264 (zerolatency, medium, 8 slices, no B-frames; bpp / PSNR): " + ", ".join(f"{b:.3f} / {p:.1f}" for b, p in xc))
    xb = {t: rd.bits_at(xc, t) for t in (35, 38)}
    rows = []
    full = curve(ALL)
    rows.append(("SL2 (all tools)", full))
    print("  SL2 all tools (bpp / PSNR): " + ", ".join(f"{b:.3f} / {p:.1f}" for b, p in full))
    for name, bit in TOOLS:
        rows.append((f"SL2 without {name}", curve(ALL & ~bit)))
    cum = 0
    rows.append(("SL1-like (no tools)", curve(0)))
    for name, bit in TOOLS:
        cum |= bit
        rows.append((f"  + {name} (cumulative)", curve(cum)))
    print("\n  configuration                     bpp@35dB  ratio   bpp@38dB  ratio")
    out = {}
    for name, cv in rows:
        a35, a38 = rd.bits_at(cv, 35), rd.bits_at(cv, 38)
        out[name] = (a35, a38)
        f = lambda a, t: ("   n/a   " if a is None else f"{a:7.4f}  {a / xb[t]:5.2f}")      # noqa: E731
        print(f"  {name:<32} {f(a35, 35)}   {f(a38, 38)}")
    print(f"  x264                              {xb[35]:7.4f}   1.00   {xb[38]:7.4f}   1.00")
    print("  (module 29, SL1 in Python: ratio 6.8 at 35 dB and 7.6 at 38 dB)")
    a35, a38 = out["SL2 (all tools)"]
    for t, a in ((35, a35), (38, a38)):
        r = a / xb[t]
        print(f"  R32-08 ratio to x264 at {t} dB: {r:.2f} -> {'met' if r <= 2.0 else 'NOT MET'} (target 2.0)")
    assert a35 is not None and a38 is not None


# ---------------------------------------------------------------- T32-06
def loss_run(args):
    seed, refresh, nf, loss_p = args
    seq = rd.get_seq(1, nf)
    c = sl2.Codec(W, H, 16, ALL)
    rng = random.Random(seed)
    ns = c.ns
    ref_e = ref_d = None
    bits, ps = 0, []
    prev_lost = set()
    for k, f in enumerate(seq):
        intra = prev_lost if refresh else set()
        sl, rec, _ = c.encode_frame(f, ref_e, qp=30, intra=intra)
        bits += sum(len(b) for b in sl) * 8
        lost = {s for s in range(ns) if k > 0 and rng.random() < loss_p}
        dec = c.decode_frame([None if s in lost else b for s, b in enumerate(sl)], ref_d)
        ps.append(rd.psnr(f, dec))
        ref_e, ref_d = rec, dec
        prev_lost = lost
    return bits / nf / rd.BPP, float(np.mean(ps))


def single_loss():
    seq = rd.get_seq(2, 12)
    c = sl2.Codec(W, H, SH, ALL)
    res = {}
    for refresh in (False, True):
        ref_e = ref_d = None
        rows = []
        for k, f in enumerate(seq):
            intra = {3} if (refresh and k == 7) else set()
            sl, rec, _ = c.encode_frame(f, ref_e, qp=30, intra=intra)
            lost = {3} if k == 6 else set()
            dec = c.decode_frame([None if s in lost else b for s, b in enumerate(sl)], ref_d)
            rows.append(rd.psnr(f[3 * SH:4 * SH], dec[3 * SH:4 * SH]))
            ref_e, ref_d = rec, dec
        res[refresh] = rows
    return res


def t06():
    print("T32-06 reactive refresh")
    r = single_loss()
    fmt = lambda v: " ".join(f"{x:.1f}" for x in v[4:12])        # noqa: E731
    print(f"  slice 3 lost in frame 6; PSNR of its rows in frames 4..11 (dB): without refresh {fmt(r[False])}; with the refresh path (intra in frame 7) {fmt(r[True])}")
    assert r[True][7] > r[False][7] + 3 and r[True][7] > r[True][5] - 2.5
    with Pool(3) as p:
        free, nore, ref = p.map(loss_run, [(1, False, 30, 0.0), (1, False, 30, 0.05), (1, True, 30, 0.05)])
    print(f"  30 frames, 16 slices, 5% slice loss: loss-free {free[0]:.4f} bpp / {free[1]:.2f} dB; with refresh {ref[0]:.4f} bpp ({ref[0] / free[0]:.3f} of the loss-free rate) / {ref[1]:.2f} dB; without refresh {nore[0]:.4f} bpp / {nore[1]:.2f} dB")
    assert ref[1] > nore[1] + 2 and ref[1] > free[1] - 0.5


# ---------------------------------------------------------------- T32-07
def fov_run(args):
    qp, fov, si = args
    seq = rd.get_seq(si, 8)
    c = sl2.Codec(W, H, SH, ALL)
    dqp = fov_map() if fov else None
    ref, bits, pc, pp = None, 0, [], []
    yy, xx = np.mgrid[0:H, 0:W]
    centre = (np.hypot(xx - W / 2, yy - H / 2) <= 48)
    for f in seq:
        sl, rec, _ = c.encode_frame(f, ref, qp=qp, dqp=dqp)
        bits += sum(len(b) for b in sl) * 8
        mse_c = np.mean((f[centre].astype(float) - rec[centre]) ** 2)
        mse_p = np.mean((f[~centre].astype(float) - rec[~centre]) ** 2)
        pc.append(10 * np.log10(255 ** 2 / mse_c))
        pp.append(10 * np.log10(255 ** 2 / mse_p))
        ref = rec
    return bits / 8 / rd.BPP, float(np.mean(pc)), float(np.mean(pp))


def t07():
    print("T32-07 foveation")
    qps = [20, 24, 28, 32, 36, 40]
    with Pool(12) as p:
        uni = p.map(fov_run, [(q, False, 0) for q in qps])
        fv = p.map(fov_run, [(q, True, 0) for q in qps])
    cu = [(b, pc) for b, pc, _ in uni]
    cf = [(b, pc) for b, pc, _ in fv]
    lo = max(min(p for _, p in cu), min(p for _, p in cf))
    hi = min(max(p for _, p in cu), max(p for _, p in cf))
    tgt = round((lo + hi) / 2, 1)
    bu, bf = rd.bits_at(cu, tgt), rd.bits_at(cf, tgt)
    print(f"  centre disc (radius 48 px of the 56 px map), uniform QP against QP offset up to +10 outside a 56 px disc: at equal centre PSNR {tgt} dB the foveated stream needs {bf:.4f} bpp against {bu:.4f} bpp ({100 * (1 - bf / bu):.0f}% fewer bits)")
    pu = np.interp(tgt, sorted(p for _, p in cu), [pp for _, pc, pp in sorted(uni, key=lambda r: r[1])])
    pf = np.interp(tgt, sorted(p for _, p in cf), [pp for _, pc, pp in sorted(fv, key=lambda r: r[1])])
    print(f"  periphery PSNR at that point: uniform {pu:.1f} dB, foveated {pf:.1f} dB")
    assert bf < bu


# ---------------------------------------------------------------- T32-09
def t09():
    print("T32-09 complexity")
    b, ps, st = rd.run_sl2((ALL, 30, 0, rd.NF))
    npx = rd.NF * rd.W * rd.H
    print(f"  measured at QP 30, {rd.NF} frames of {rd.W} x {rd.H}: {st['bins'] / npx:.3f} coded bins per pixel, {st['probes'] / npx * 64:.2f} RDO trial blocks per 64 pixels, {st['sad_evals'] / npx * 64:.0f} motion-search SAD evaluations per 8 x 8 block, {st['encodes'] / rd.NF / 8:.1f} slice encodes per slice")
    b0, ps0, st0 = rd.run_sl2((0, 30, 0, rd.NF))
    print(f"  SL1-like settings (no tools): {st0['bins'] / npx:.3f} bins per pixel, {st0['probes'] / npx * 64:.2f} trial blocks per 64 pixels, {st0['sad_evals'] / npx * 64:.0f} SAD evaluations per block")
    print(f"  1080p60 = 124.4 Mpixel/s: decoder {st['bins'] / npx * 124.4:.0f} Mbins/s of arithmetic decoding at this QP; per decoded pixel one 8 x 8 inverse DCT (partial butterflies: 22 multiplications and 28 additions per 8-point pass, 16 passes per 64 pixels = 0.34 multiplications and 0.44 additions per pixel per pass pair), one interpolation (6-tap half-pel: 6 taps per sample, quarter-pel adds one average), deblocking (about 1 filter-line decision per pixel edge)")


if __name__ == "__main__":
    which = sys.argv[1:] or ["t01", "t02", "t03", "t04", "t05", "t06", "t07", "t09"]
    for w in which:
        globals()[w]()
    print("\nSL2 TESTS PASSED")
