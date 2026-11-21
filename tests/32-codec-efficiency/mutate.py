"""M-32: mutation checks of the SL2 reference model. Each mutant must fail T32-01 (transform) or the closed-loop test (T32-02).
Decoder-side mutants (guarded by `!s->src`) show that the closed-loop test checks the decoder against the encoder tool by tool.
Usage: python3 mutate.py"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FW = HERE.parents[1] / "fw" / "32-codec"
MUT = {
    "a_dct_constant": ("{89, 75, 50, 18, -18, -50, -75, -89}", "{89, 74, 50, 18, -18, -50, -74, -89}"),
    "b_dequant_rounding_decoder": ("c[pos] = dct ? (lev[k] * DQ[qp] + 8) >> 4 : lev[k] * SH_[qp][pos];", "c[pos] = dct ? (lev[k] * DQ[qp] + (s->src ? 8 : 7)) >> 4 : lev[k] * SH_[qp][pos];"),
    "c_mv_median_decoder": ("    *px = MED(ax, bxv, cx);", "    *px = MED(ax, bxv, cx) + (s->src ? 0 : 1);"),
    "d_plane_constant_decoder": ("int a = 16 * (L[8] + T[8]), b = (17 * Hs + 16) >> 5, c = (17 * Vs + 16) >> 5;", "int a = 16 * (L[8] + T[8]), b = (17 * Hs + (s->src ? 16 : 15)) >> 5, c = (17 * Vs + 16) >> 5;"),
    "e_quarter_pel_phase_decoder": ("fx = mvx & 3, fy = mvy & 3;", "fx = (mvx + (s->src ? 0 : 1)) & 3, fy = mvy & 3;"),
    "f_context_not_reset_decoder": ("    ctx_init(&s->cx);\n    return s->cur", "    if (src) ctx_init(&s->cx);\n    return s->cur"),
    "g_deblock_strength_decoder": ("    if (cfg->tools & SL2_T_DEBLOCK) deblock(&s);\n    for (int y = 0; y < s.SH; y++) memcpy(recon + (s.y0 + y) * s.W, s.cur + y * s.W, s.W);\n    sl_close(&s);\n    return 0;", "    if (cfg->tools & SL2_T_DEBLOCK) { deblock(&s); for (int i = 0; i < 8; i++) s.cur[3 * s.W + 8 + i]++; }\n    for (int y = 0; y < s.SH; y++) memcpy(recon + (s.y0 + y) * s.W, s.cur + y * s.W, s.W);\n    sl_close(&s);\n    return 0;"),
    "h_skip_context_merged_decoder": ("int sk = bin(c, &x->skip[n_skip], V(c, b->kind == 0));", "int sk = bin(c, &x->skip[s->src ? n_skip : 0], V(c, b->kind == 0));"),
}
RUN = '''
import sys
sys.path.insert(0, %r)
import test_sl2 as T
T.t01()
r = T.closed_loop((T.ALL, False, True, 4))
assert r == "ok", r
r = T.closed_loop((T.ALL, True, False, 3))
assert r == "ok", r
print("PASS")
'''


def main():
    fail = 0
    for k, (old, new) in MUT.items():
        src = (FW / "sl2.c").read_text()
        assert src.count(old) == 1, f"{k}: pattern found {src.count(old)} times"
        d = Path(tempfile.mkdtemp(prefix="mut32_"))
        (d / "sl2.c").write_text(src.replace(old, new))
        shutil.copy(FW / "sl2.h", d / "sl2.h")
        shutil.copy(FW / "sl2.py", d / "sl2.py")
        env = dict(os.environ, SL2_DIR=str(d))
        r = subprocess.run([sys.executable, "-c", RUN % str(HERE)], env=env, capture_output=True, text=True, cwd=str(HERE))
        killed = "PASS" not in r.stdout
        print(f"  {k:<32} {'killed' if killed else 'SURVIVED'}" + (f" ({(r.stderr.strip().splitlines() or r.stdout.strip().splitlines() or [''])[-1][:100]})" if killed else ""))
        fail += not killed
        shutil.rmtree(d, ignore_errors=True)
    print("MUTATION", "PASSED" if not fail else "FAILED")
    return fail


if __name__ == "__main__":
    sys.exit(main())
