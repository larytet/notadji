import math
import sys
import traceback

import numpy as np

sys.path.insert(0, "/home/arkady/notadji/scripts")
import dpdmodel as M
import sysmodel as S
import gen_cfr_tables as gct

TESTS = []
LIB = S.load_fw()


def test(f):
    TESTS.append(f)
    return f


def norm_int(x, rms):
    x = x / np.sqrt(np.mean(np.abs(x) ** 2)) * rms
    return np.round(x.real * 32768).astype(np.int64), np.round(x.imag * 32768).astype(np.int64)


@test
def t26_03_cfr_chain_model():
    rng = np.random.default_rng(2603)
    # the vectorised models equal the scalar (RTL-verified) models
    xs = [(int(rng.integers(-9000, 9000)), int(rng.integers(-9000, 9000))) for _ in range(1500)]
    xi = np.array([a for a, b in xs], dtype=np.int64)
    xq = np.array([b for a, b in xs], dtype=np.int64)
    t1, t2 = gct.clip_table(0.2), gct.clip_table(0.25)
    ci, cq = S.chain_np(xi, xq, t1, t2)
    assert list(zip(ci.tolist(), cq.tolist())) == M.chain_model(xs, t1, t2), "chain: vectorised model differs from the scalar model"
    a = [(int(rng.integers(2500, 5500)),) + (int(rng.integers(-500, 500)),) for _ in range(9)]
    di, dq = S.dpd_np(xi, xq, a)
    assert list(zip(di.tolist(), dq.tolist())) == M.dpd_model(xs, a)
    re, im = S.corr_np(xi[:300], xq[:300], xi[1:301], xq[1:301])
    ref = M.corr_model([(xs[k], xs[k + 1]) for k in range(300)])
    assert [[r, i] for r, i in zip(re, im)] == ref
    # PAPR, EVM and out-of-band power against the threshold
    x, data = S.ofdm(rng, 120)
    xi, xq = norm_int(x, 0.31)
    ref_x = (xi + 1j * xq) / 32768
    rows = []
    p0 = S.papr_ccdf(ref_x)
    for a_ in (0.55, 0.60, 0.65, 0.70):
        ci, cq = S.chain_np(xi, xq, gct.clip_table(a_), gct.clip_table(a_ * 1.03))
        c = (ci + 1j * cq) / 32768
        scale = np.sqrt(np.mean(np.abs(ref_x) ** 2) / np.mean(np.abs(c) ** 2))
        rows.append((a_, S.papr_ccdf(c), S.evm_db(c * scale, data), S.aclr_db(c)))
    paprs = [r[1] for r in rows]
    assert all(b > a for a, b in zip(paprs, paprs[1:])), paprs
    assert rows[2][2] <= -30 and all(r[3] <= -45 for r in rows)
    return (f"vectorised models equal the scalar models; PAPR at 1e-3 of the unclipped signal {p0:.2f} dB; threshold (fraction of full scale) / PAPR / CFR-only EVM / ACLR of the CFR output: " +
            "; ".join(f"{a_} / {p:.2f} dB / {e:.1f} dB / {c:.1f} dBc" for a_, p, e, c in rows))


@test
def t26_06_solver():
    rng = np.random.default_rng(2606)
    worst = 0
    worst_lstsq = 0
    out_err = 0
    for trial in range(10):
        a_true = [(int(rng.integers(2500, 5500)), int(rng.integers(-600, 600)))] + [(int(rng.integers(-900, 900)), int(rng.integers(-900, 900))) for _ in range(8)]
        x = (rng.normal(0, 0.24, 6000) + 1j * rng.normal(0, 0.24, 6000))
        yi = np.clip(np.round(x.real * 32768), -32768, 32767).astype(np.int64)
        yq = np.clip(np.round(x.imag * 32768), -32768, 32767).astype(np.int64)
        ui, uq = S.dpd_np(yi, yq, a_true)                     # the exact output of the model: the solver must find a_true
        sl = slice(100, 4196)
        re, im = S.corr_np(yi[sl], yq[sl], ui[sl], uq[sl])
        st, got = S.solve(LIB, re, im, 4096, 1e-7)
        assert st == 0, f"status {st}"
        err = max(max(abs(g[0] - t[0]), abs(g[1] - t[1])) for g, t in zip(got, a_true))
        worst = max(worst, err)
        # the same accumulators in double precision with numpy (same Jacobi scaling and relative loading)
        A = np.zeros((9, 9), complex)
        e = 0
        for p in range(9):
            for q in range(p, 9):
                A[p, q] = (re[e] + 1j * im[e]) / (4096 * 2 ** 30)
                A[q, p] = np.conj(A[p, q])
                e += 1
        c = np.array([(re[e + p] + 1j * im[e + p]) / (4096 * 2 ** 30) for p in range(9)])
        d = np.sqrt(np.diag(A).real)
        As = A / np.outer(d, d) + 1e-7 * np.eye(9)
        sol = np.linalg.solve(As, c / d) / d * 4096
        worst_lstsq = max(worst_lstsq, max(abs(sol.real[t] - got[t][0]) for t in range(9)), max(abs(sol.imag[t] - got[t][1]) for t in range(9)))
        # output-domain error on fresh samples
        x2 = (rng.normal(0, 0.24, 3000) + 1j * rng.normal(0, 0.24, 3000))
        zi = np.clip(np.round(x2.real * 32768), -32768, 32767).astype(np.int64)
        zq = np.clip(np.round(x2.imag * 32768), -32768, 32767).astype(np.int64)
        o1 = S.dpd_np(zi, zq, got)
        o2 = S.dpd_np(zi, zq, a_true)
        e_out = np.sqrt(np.mean((o1[0] - o2[0]) ** 2 + (o1[1] - o2[1]) ** 2)) / np.sqrt(np.mean(o2[0] ** 2 + o2[1] ** 2))
        out_err = max(out_err, e_out)
    assert 20 * math.log10(out_err) <= -45, f"output error {20 * math.log10(out_err):.1f} dB"
    assert worst_lstsq <= 6.0, f"float32 against double: {worst_lstsq}"
    # noisy observation
    errs = []
    for trial in range(10):
        a_true = [(4096, 0)] + [(int(rng.integers(-500, 500)), int(rng.integers(-500, 500))) for _ in range(8)]
        x = (rng.normal(0, 0.24, 6000) + 1j * rng.normal(0, 0.24, 6000))
        yi = np.clip(np.round(x.real * 32768), -32768, 32767).astype(np.int64)
        yq = np.clip(np.round(x.imag * 32768), -32768, 32767).astype(np.int64)
        ui, uq = S.dpd_np(yi, yq, a_true)
        sigma = 32768 * 0.24 * math.sqrt(2) * 10 ** (-40 / 20) / math.sqrt(2)
        ui = ui + np.round(rng.normal(0, sigma, len(ui))).astype(np.int64)
        uq = uq + np.round(rng.normal(0, sigma, len(uq))).astype(np.int64)
        sl = slice(100, 4196)
        re, im = S.corr_np(yi[sl], yq[sl], ui[sl], uq[sl])
        st, got = S.solve(LIB, re, im, 4096, 1e-5)
        errs.append(max(max(abs(g[0] - t[0]), abs(g[1] - t[1])) for g, t in zip(got, a_true)))
    # singular input
    st, _ = S.solve(LIB, [0] * 54, [0] * 54, 4096, 1e-4)
    assert st == 2, st
    st0, _ = S.solve(LIB, [0] * 54, [0] * 54, 0, 1e-4)
    assert st0 == 1
    return (f"noise-free fit: output error {20 * math.log10(out_err):.1f} dB relative to the true model's output on fresh samples (coefficient error up to {worst} LSB of Q4.12 for the weak high-order terms, which the output hardly depends on), float32 against double precision within {worst_lstsq:.2f} LSB; "
            f"at 40 dB observation SNR the worst coefficient error over 10 runs is {max(errs):.0f} LSB (mean {np.mean(errs):.0f}); an all-zero accumulator returns the singular status")


def make_run(a_thr, rms, rng_seed=5, N=4096, noise_db=-45, asat=0.7, pa_gain=1.0, ridge=1e-4):
    xs0, dat = S.ofdm(np.random.default_rng(rng_seed), 120)
    xt, _ = S.ofdm(np.random.default_rng(9), 12)

    def prep(x):
        i, q = norm_int(x, rms)
        if a_thr is not None:
            i, q = S.chain_np(i, q, gct.clip_table(a_thr), gct.clip_table(a_thr * 1.03))
        return i, q

    ei, eq = prep(xs0)
    ti, tq = prep(xt)

    def evaluate(A, gain):
        ui, uq = S.dpd_np(ei, eq, A)
        yo = S.pa(gain * (ui + 1j * uq) / 32768, asat)
        return S.evm_db(yo, dat), S.aclr_db(yo)

    def iterate(A, it, gain, first):
        ui, uq = S.dpd_np(ti, tq, A)
        u = (ui + 1j * uq) / 32768
        yt = S.pa(gain * u, asat)
        nz = 10 ** (noise_db / 20) * np.sqrt(np.mean(np.abs(yt) ** 2))
        r = np.random.default_rng(1000 + it)
        yt = yt + nz * (r.normal(size=len(yt)) + 1j * r.normal(size=len(yt))) / np.sqrt(2)
        g = np.sum(yt * np.conj(u)) / np.sum(np.abs(u) ** 2)                # complex gain alignment (firmware)
        yn = yt / g
        yi = np.round(yn.real * 32768).astype(np.int64)
        yq = np.round(yn.imag * 32768).astype(np.int64)
        sl = slice(500, 500 + N)
        re, im = S.corr_np(yi[sl], yq[sl], ui[sl], uq[sl])
        st, P = S.solve(LIB, re, im, N, ridge)
        assert st in (0, 3), f"solver status {st}"
        mu = 1.0 if first else 0.5
        return [(int(round(A[t][0] + (P[t][0] - A[t][0]) * mu)), int(round(A[t][1] + (P[t][1] - A[t][1]) * mu))) for t in range(9)], P

    return evaluate, iterate


@test
def t26_07_system():
    ident = [(4096, 0)] + [(0, 0)] * 8
    rows = []
    for rms, a_thr in ((0.313, 0.66), (0.313, 0.70), (0.30, 0.66), (0.29, 0.66), (0.26, 0.70)):
        ev, it = make_run(a_thr, rms)
        A = ident
        trace = [ev(A, 1.0)]
        for k in range(6):
            A, _ = it(A, k, 1.0, k == 0)
            trace.append(ev(A, 1.0))
        rows.append((rms, a_thr, trace))
    # no correction, CFR only, DPD only, both at the 7.4 dB point
    rms = 0.30
    ev_none, _ = make_run(None, rms)
    base = ev_none(ident, 1.0)
    ev_cfr, _ = make_run(0.66, rms)
    cfr_only = ev_cfr(ident, 1.0)
    ev_dpd, it_dpd = make_run(None, rms)
    A = ident
    for k in range(6):
        A, _ = it_dpd(A, k, 1.0, k == 0)
    dpd_only = ev_dpd(A, 1.0)
    both = [r for r in rows if r[0] == 0.30][0][2][-1]
    # convergence: the figures change by less than 0.3 dB between iterations 4 and 5
    tr = [r for r in rows if r[0] == 0.30][0][2]
    assert abs(tr[5][0] - tr[4][0]) < 0.3 and abs(tr[5][1] - tr[4][1]) < 0.3, tr
    assert tr[2][1] <= tr[0][1] - 8, "no improvement in two iterations"
    # the specification point: 7.4 dB back-off, both limits
    assert both[0] <= -32 and both[1] <= -45, f"EVM {both[0]:.1f} dB, ACLR {both[1]:.1f} dBc"
    # tracking: the PA gain drops by 1 dB; the loop re-converges in 3 iterations
    ev, it = make_run(0.66, 0.30)
    A = ident
    for k in range(6):
        A, _ = it(A, k, 1.0, k == 0)
    before = ev(A, 1.0)
    hit = ev(A, 10 ** (-1 / 20))
    for k in range(3):
        A, _ = it(A, 10 + k, 10 ** (-1 / 20), False)
    after = ev(A, 10 ** (-1 / 20))
    # time per iteration (the RTL clocks come from the tests of dpd_corr: 58 clocks per sample)
    n = 4096
    t_capture = n / 80e6
    t_corr = n * 58 / 200e6
    t_solve = 12e3 / 50e6            # about 12 kflop of float32 work at 50 Mflop/s [E]
    t_it = t_capture + t_corr + t_solve
    n_conv = 3
    t_cold = n_conv * t_it
    assert t_cold < 0.2, t_cold
    s = "; ".join(f"back-off {20 * math.log10(0.7 / r):.1f} dB, clip {a}: {t[0][0]:.1f}/{t[0][1]:.1f} -> {t[-1][0]:.1f}/{t[-1][1]:.1f} (after {len(t) - 1} iterations, EVM dB / ACLR dBc)" for r, a, t in rows)
    return (s + f". At 7.4 dB back-off: nothing {base[0]:.1f}/{base[1]:.1f}, CFR only {cfr_only[0]:.1f}/{cfr_only[1]:.1f}, DPD only {dpd_only[0]:.1f}/{dpd_only[1]:.1f}, both {both[0]:.1f}/{both[1]:.1f}. "
            f"Convergence: ACLR after iterations 0, 1, 2, 3: " + ", ".join(f"{x[1]:.1f}" for x in tr[:4]) + f". Tracking: a 1 dB PA gain drop changes the figures from {before[0]:.1f}/{before[1]:.1f} to {hit[0]:.1f}/{hit[1]:.1f} and 3 iterations restore {after[0]:.1f}/{after[1]:.1f}. "
            f"Time per iteration {t_it * 1e3:.2f} ms (capture {t_capture * 1e6:.0f} us, dpd_corr {t_corr * 1e3:.2f} ms, solver about {t_solve * 1e6:.0f} us), cold start of {n_conv} iterations {t_cold * 1e3:.1f} ms against 200 ms")


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
            traceback.print_exc(limit=3, file=sys.stdout)
    print("ALL TESTS PASSED" if rc == 0 else "SOME TESTS FAILED")
    sys.exit(rc)
