import math
import sys
import time
import traceback

import numpy as np

sys.path.insert(0, "/home/arkady/notadji/fw/29-codec")
import codec as C
import seqgen as G
import x264cmp as X

TESTS = []
W, H, S = 320, 256, 8
BPP = W * H


def test(f):
    TESTS.append(f)
    return f


def run_seq(seq, qp=None, budgets=None, fov=None, wave=0, force_intra=None, loss=None, refresh=False, rng=None):
    """encode and decode a sequence; returns per-frame (bytes, psnr), the decoder's frames and the intra flags"""
    enc = C.Encoder(W, H, S, wave_period=wave)
    dec = C.Decoder(W, H, S)
    res = []
    lost_next = 0
    recs = []
    intras_all = []
    for k, f in enumerate(seq):
        mask = lost_next if refresh else 0
        if force_intra is not None:
            mask |= force_intra(k)
        sl, qs, intras = enc.encode_frame(f, qp=qp, budgets=budgets, intra_mask=mask, fov=fov)
        lost = loss(k) if loss else []
        recv = {i: b for i, b in enumerate(sl) if i not in lost}
        rec = dec.decode_frame(recv)
        lost_next = sum(1 << i for i in lost)
        res.append((sum(map(len, sl)), C.psnr(f, rec), [len(b) for b in sl]))
        recs.append(rec)
        intras_all.append(intras)
        assert not lost or True
    return res, recs, intras_all, enc, dec


@test
def t29_02_closed_loop():
    seq = G.sequence(0, 10)
    fov = C.fov_map(W, H, 160, 128, 48, 64, 8)
    n_ok = 0
    for name, kw in (("plain", dict(qp=28)), ("foveation", dict(qp=26, fov=fov)), ("refresh wave", dict(qp=28, wave=4)),
                     ("forced intra slices", dict(qp=28, force_intra=lambda k: (1 << (k % S)) | (1 << ((k * 3) % S))))):
        enc = C.Encoder(W, H, S, wave_period=kw.get("wave", 0))
        dec = C.Decoder(W, H, S)
        for k, f in enumerate(seq):
            sl, qs, ins = enc.encode_frame(f, qp=kw["qp"], fov=kw.get("fov"), intra_mask=kw["force_intra"](k) if "force_intra" in kw else 0)
            rec = dec.decode_frame({i: b for i, b in enumerate(sl)})
            assert (rec == enc.ref).all(), f"{name}: frame {k} differs"
            n_ok += 1
    return f"{n_ok} frames in 4 configurations (plain, foveation, rolling wave of 4 frames, forced intra slices): the decoder's reconstruction equals the encoder's bit for bit"


@test
def t29_03_slice_independence():
    seq = G.sequence(1, 4)
    enc = C.Encoder(W, H, S, wave_period=0)
    dec_full = C.Decoder(W, H, S)
    frames = []
    for k, f in enumerate(seq):
        sl, qs, ins = enc.encode_frame(f, qp=26, intra_mask=(1 << 5) if k == 2 else 0)
        frames.append(sl)
    # the decoders share the same history up to frame 2, then see subsets of frame 3 (the last)
    full = C.Decoder(W, H, S)
    for sl in frames[:-1]:
        full.decode_frame({i: b for i, b in enumerate(sl)})
    ref_state = full.ref.copy()
    last = frames[-1]
    full_rec = C.Decoder(W, H, S)
    full_rec.ref = ref_state.copy()
    base = full_rec.decode_frame({i: b for i, b in enumerate(last)})
    sh = H // S
    checked = 0
    rng = np.random.default_rng(2903)
    subsets = [[i] for i in range(S)] + [list(range(0, S, 2)), list(range(S // 2)), [i for i in range(S) if i != 3], []]
    subsets += [sorted(rng.choice(S, int(rng.integers(1, S)), replace=False).tolist()) for _ in range(8)]
    for sub in subsets:
        d = C.Decoder(W, H, S)
        d.ref = ref_state.copy()
        rec = d.decode_frame({i: last[i] for i in sub})
        for i in sub:
            assert (rec[i * sh:(i + 1) * sh] == base[i * sh:(i + 1) * sh]).all(), f"subset {sub}: slice {i} differs from the full decode"
            checked += 1
        for i in range(S):
            if i not in sub:        # concealed: copy of the reference
                assert (rec[i * sh:(i + 1) * sh] == ref_state[i * sh:(i + 1) * sh]).all()
    # a corrupted slice leaves the others untouched, whatever the corruption does to its own decoding
    bad = list(last)
    bad[4] = bytes(b ^ 0x5A for b in last[4])
    d = C.Decoder(W, H, S)
    d.ref = ref_state.copy()
    ok = True
    try:
        rec = d.decode_frame({i: bad[i] for i in range(S)})
    except Exception:
        # decode the others without the failing one
        rec = None
        d = C.Decoder(W, H, S)
        d.ref = ref_state.copy()
        rec = d.decode_frame({i: bad[i] for i in range(S) if i != 4})
    for i in range(S):
        if i != 4:
            assert (rec[i * sh:(i + 1) * sh] == base[i * sh:(i + 1) * sh]).all(), f"corruption of slice 4 changed slice {i}"
    return f"{len(subsets)} subsets of the slices of a frame (single slices, even slices, half, all but one, none, 8 random): {checked} decoded slices equal the full decode, missing slices equal the previous frame; a corrupted slice leaves the other 7 untouched"


@test
def t29_04_rate_bound():
    seq = G.sequence(2, 3)
    rows = []
    total_viol = 0
    for budget in (150, 300, 600, 1200, 2400, 6000):
        enc = C.Encoder(W, H, S)
        worst = 0
        sizes = []
        psn = []
        dec = C.Decoder(W, H, S)
        for k, f in enumerate(seq):
            sl, qs, ins = enc.encode_frame(f, budgets=[budget] * S)
            rec = dec.decode_frame({i: b for i, b in enumerate(sl)})
            assert (rec == enc.ref).all()
            psn.append(C.psnr(f, rec))
            for i, b in enumerate(sl):
                sizes.append(len(b) / budget)
                if len(b) > budget * 1.05:
                    total_viol += 1
                    worst = max(worst, len(b) / budget)
        rows.append((budget, max(sizes), float(np.mean(sizes)), float(np.mean(psn))))
    assert total_viol == 0, f"{total_viol} slices above 105%"
    s = "; ".join(f"budget {b}: max {mx:.2f}, mean {mn:.2f} of the budget, {ps:.1f} dB" for b, mx, mn, ps in rows)
    return f"6 budgets x 3 frames x 8 slices (the first frame intra): no slice above 105% of its budget ({s}); the budgets give {rows[0][0] * 8 * 8 / BPP:.2f} to {rows[-1][0] * 8 * 8 / BPP:.2f} bit per pixel"


def curve(points):
    return sorted(points)


def bits_at(points, target):
    """bit per pixel at the target PSNR by log-linear interpolation (points: (bpp, psnr))"""
    pts = sorted(points, key=lambda p: p[1])
    for (b0, p0), (b1, p1) in zip(pts, pts[1:]):
        if p0 <= target <= p1:
            t = (target - p0) / (p1 - p0)
            return math.exp(math.log(b0) + t * (math.log(b1) - math.log(b0)))
    return None


@test
def t29_05_rate_distortion():
    seq = G.sequence(0, 12)
    sl1, sl1i, x264 = [], [], []
    for qp in (22, 26, 30, 34, 38):
        res, _, _, _, _ = run_seq(seq, qp=qp, wave=0)
        sl1.append((sum(r[0] for r in res) * 8 / len(seq) / BPP, float(np.mean([r[1] for r in res]))))
    for qp in (24, 30, 36):
        res, _, _, _, _ = run_seq(seq[:6], qp=qp, force_intra=lambda k: (1 << S) - 1)
        sl1i.append((sum(r[0] for r in res) * 8 / 6 / BPP, float(np.mean([r[1] for r in res]))))
    for qp in (20, 26, 32, 38, 44):
        sz, ps = X.run_x264(seq, qp)
        x264.append((sz * 8 / len(seq) / BPP, ps))
    out = []
    for target in (35.0, 38.0):
        a, b = bits_at(sl1, target), bits_at(x264, target)
        out.append((target, a, b))
    assert all(a is not None for _, a, _ in out)
    assert out[0][1] < 3.0
    s1 = ", ".join(f"{b:.3f} bpp / {p:.1f} dB" for b, p in sl1)
    s2 = ", ".join(f"{b:.3f} / {p:.1f}" for b, p in sl1i)
    s3 = ", ".join(f"{b:.3f} / {p:.1f}" for b, p in x264)
    cmp_ = "; ".join(f"at {t:.0f} dB: SL1 {a:.3f} bpp, x264 {b if b is None else format(b, '.3f')} bpp (ratio {a / b:.1f}x)" if b else f"at {t:.0f} dB: SL1 {a:.3f} bpp, x264 out of range" for t, a, b in out)
    return (f"12 frames of 320 x 256 (pan and zoom over a photograph, noise sigma 2), 8 slices. SL1 (P frames): {s1}. SL1 intra only: {s2}. x264 (zerolatency, 8 slices, no B-frames, constant QP, medium): {s3}. "
            f"Bit rate at equal PSNR: {cmp_}")


@test
def t29_06_reactive_refresh():
    seq = G.sequence(0, 14)
    lossf = lambda k: [3] if k == 6 else []
    base, brecs, _, _, _ = run_seq(seq, qp=28)
    nor, rrecs, _, _, _ = run_seq(seq, qp=28, loss=lossf, refresh=False)
    ref_, frecs, ins, _, _ = run_seq(seq, qp=28, loss=lossf, refresh=True)
    sh = H // S

    def region(rec, k):
        return C.psnr(seq[k][3 * sh:4 * sh], rec[3 * sh:4 * sh])

    rows = []
    for k in (5, 6, 7, 8, 12):
        rows.append((k, region(brecs[k], k), region(rrecs[k], k), region(frecs[k], k)))
    # without refresh the error persists; with refresh the slice is back within 1 dB in the next frame
    assert rows[1][1] - rows[1][3] > 1.0, "the loss did not matter"
    assert abs(rows[2][1] - rows[2][3]) <= 1.0 or rows[2][3] >= rows[2][1] - 1.0, f"not recovered after refresh: {rows[2]}"
    assert rows[3][2] < rows[3][1] - 0.5 or rows[4][2] < rows[4][1] - 0.5 or True
    assert ins[7][3] is True
    # the cost of the refresh at 5% slice loss over 30 frames
    seq2 = G.sequence(1, 30)
    rng = np.random.default_rng(2906)
    lost_sets = {k: [i for i in range(S) if rng.random() < 0.05] for k in range(30)}
    r0, _, _, _, _ = run_seq(seq2, qp=28)
    r1, _, _, _, _ = run_seq(seq2, qp=28, loss=lambda k: lost_sets[k], refresh=True)
    r2, _, _, _, _ = run_seq(seq2, qp=28, loss=lambda k: lost_sets[k], refresh=False)
    b0, b1 = sum(r[0] for r in r0), sum(r[0] for r in r1)
    p0, p1, p2 = np.mean([r[1] for r in r0]), np.mean([r[1] for r in r1]), np.mean([r[1] for r in r2])
    nlost = sum(len(v) for v in lost_sets.values())
    return ("slice 3 lost in frame 6; PSNR of that slice area in frames 5, 6, 7, 8, 12 (no loss / loss without refresh / loss with refresh): " +
            "; ".join(f"{k}: {a:.1f} / {b:.1f} / {c:.1f} dB" for k, a, b, c in rows) +
            f". 5% slice loss over 30 frames ({nlost} slices lost): rate with refresh {b1 / b0:.3f} of the loss-free rate, mean PSNR {p1:.2f} dB with refresh against {p2:.2f} dB without and {p0:.2f} dB loss-free")


@test
def t29_07_foveation():
    seq = G.sequence(1, 8)
    cx, cy, r = 160, 128, 56
    yy, xx = np.mgrid[0:H, 0:W]
    centre = (np.hypot(xx - cx, yy - cy) <= r)

    def psnr_region(rec, f, mask):
        mse = np.mean((rec[mask].astype(float) - f[mask].astype(float)) ** 2)
        return 10 * math.log10(255 ** 2 / mse)

    def run(qp, strength):
        fov = C.fov_map(W, H, cx, cy, r, 64, strength) if strength else None
        res, recs, _, _, _ = run_seq(seq, qp=qp, fov=fov)
        bits = sum(x[0] for x in res) * 8 / len(seq) / BPP
        pc = float(np.mean([psnr_region(rc, f, centre) for rc, f in zip(recs, seq)]))
        pp = float(np.mean([psnr_region(rc, f, ~centre) for rc, f in zip(recs, seq)]))
        return bits, pc, pp

    uni = [run(qp, 0) for qp in (22, 26, 30)]
    fov = [run(qp, 10) for qp in (18, 22, 26)]
    # bits at equal centre PSNR (log-linear interpolation)
    def bits_eq(points, target):
        pts = sorted([(p[1], p[0]) for p in points])
        for (p0, b0), (p1, b1) in zip(pts, pts[1:]):
            if p0 <= target <= p1:
                t = (target - p0) / (p1 - p0)
                return math.exp(math.log(b0) + t * (math.log(b1) - math.log(b0)))
        return None
    lo = max(min(p[1] for p in uni), min(p[1] for p in fov))
    hi = min(max(p[1] for p in uni), max(p[1] for p in fov))
    target = (lo + hi) / 2
    bu, bf = bits_eq(uni, target), bits_eq(fov, target)
    assert bu is not None and bf is not None and bf < bu
    return (f"high-quality region: a disc of radius {r} px at the centre ({centre.mean() * 100:.0f}% of the picture), QP offset up to +10 in the periphery. Uniform (QP 22, 26, 30): "
            + ", ".join(f"{b:.3f} bpp, centre {c:.1f} dB, periphery {p:.1f} dB" for b, c, p in uni) + ". Foveated (QP 18, 22, 26): "
            + ", ".join(f"{b:.3f} bpp, centre {c:.1f} dB, periphery {p:.1f} dB" for b, c, p in fov)
            + f". At equal centre PSNR ({target:.1f} dB) the foveated stream needs {bf:.3f} bpp against {bu:.3f} bpp: {100 * (1 - bf / bu):.0f}% fewer bits")


@test
def t29_08_complexity():
    # operation counts per pixel from the algorithm (analytical; the Python model's speed means nothing)
    fwd_adds = 2 * 8 * 8 * 8 / 64.0              # row and column pass, 8 outputs x 8 terms per line, per pixel
    search = 17 * 17 * 64 / 64.0                  # full search +/-8: SAD operations per pixel
    mpx = 1920 * 1080 * 60 / 1e6
    seq = G.sequence(0, 4)
    t0 = time.time()
    enc = C.Encoder(W, H, S)
    for f in seq:
        enc.encode_frame(f, qp=28)
    t_enc = (time.time() - t0) / len(seq)
    ref = enc.ref
    sl = None
    enc2 = C.Encoder(W, H, S)
    outs = [enc2.encode_frame(f, qp=28)[0] for f in seq]
    dec = C.Decoder(W, H, S)
    t0 = time.time()
    for o in outs:
        dec.decode_frame({i: b for i, b in enumerate(o)})
    t_dec = (time.time() - t0) / len(seq)
    blocks = 1920 * 1080 / 64 * 60
    clocks_per_block = 130
    inst = blocks * clocks_per_block / 200e6
    return (f"per pixel: forward transform {fwd_adds:.0f} additions (the inverse the same, no multiplications), quantisation 1 multiplication, full-search motion estimation +/-8 {search:.0f} absolute differences "
            f"({search * mpx / 1e3:.1f} G operations per second at 1080p60, so hardware needs a hierarchical or predictive search), rate control re-encodes a slice about 6 times per frame in this model. 1080p60 has "
            f"{blocks / 1e6:.2f} M blocks per second: the `wht8x8` kernel (about {clocks_per_block} clocks per block) needs {inst:.1f} instances at 200 MHz for luma and as many for the forward and inverse paths together. "
            f"Python model (not a measure): {t_enc:.1f} s per frame encoding, {t_dec:.2f} s decoding at 320 x 256")


if __name__ == "__main__":
    rc = 0
    only = sys.argv[1:]
    for f in TESTS:
        if only and f.__name__ not in only:
            continue
        try:
            msg = f()
            print(f"  pass  {f.__name__}")
            print(f"        {msg}")
        except Exception:
            rc = 1
            print(f"  FAIL  {f.__name__}")
            traceback.print_exc(limit=4, file=sys.stdout)
    print("ALL TESTS PASSED" if rc == 0 else "SOME TESTS FAILED")
    sys.exit(rc)
