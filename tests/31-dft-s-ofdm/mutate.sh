#!/bin/bash
# M-31: mutation checks of the DFT-s blocks. Each mutant must make at least one test fail.
# Usage: source scripts/sim_env.sh; tests/31-dft-s-ofdm/mutate.sh
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
D="$ROOT/tests/31-dft-s-ofdm"
rm -rf "$D/.mut"; mkdir -p "$D/.mut"
python3 - "$ROOT" "$D" <<'PY'
import sys, shutil
from pathlib import Path
root, d = Path(sys.argv[1]), Path(sys.argv[2])
R = "rtl/31-dft-s-ofdm/"
M = {
    "a_tx_no_rotation": (R + "dfts_tx.sv", ".out_rot(m_c >> 1)", ".out_rot(9'd0)"),
    "b_radix3_sign": (R + "dft_mixed.sv", "x1r = ur + vi;  x1i = ui - vr;", "x1r = ur - vi;  x1i = ui + vr;"),
    "c_ref_position": (R + "dfts_tx.sv", "wire        is_ref = (pc_q == (g_c >> 1));", "wire        is_ref = (pc_q == (g_c >> 1) + 6'd1);"),
    "d_rx_weight_not_applied": (R + "dfts_rx.sv", "wire [31:0] w_data = {sat16((pi + 48'sd128) >>> 8), sat16((pr + 48'sd128) >>> 8)};", "wire [31:0] w_data = s_axis_data;"),
    "e_scale_constant": (R + "dft_mixed.sv", "16'sd13377", "16'sd13376"),
    "f_rx_no_common_correction": (R + "dfts_rx.sv", "g_i <= sat16(48'((pg_i + 49'sd32768) >>> 16));", "g_i <= 16'sd4096;"),
    "g_rx_in_rot": (R + "dfts_rx.sv", ".in_rot(h_c[8:0])", ".in_rot(9'd0)"),
}
for k, (f, old, new) in M.items():
    src = (root / f).read_text()
    assert src.count(old) == 1, f"mutation {k}: pattern found {src.count(old)} times"
    m = d / ".mut" / k
    m.mkdir(parents=True)
    for p in d.glob("*.py"):
        shutil.copy(p, m / p.name)
    shutil.copy(d / "ds_tx_top.sv", m / "ds_tx_top.sv")
    shutil.copy(d / "ds_rx_top.sv", m / "ds_rx_top.sv")
    (m / f"mut_{Path(f).name}").write_text(src.replace(old, new))
    lines = []
    for l in (d / "sources.txt").read_text().splitlines():
        if l == f:
            l = f"tests/31-dft-s-ofdm/.mut/{k}/mut_{Path(f).name}"
        elif l.startswith("tests/31-dft-s-ofdm/ds_"):
            l = f"tests/31-dft-s-ofdm/.mut/{k}/{Path(l).name}"
        lines.append(l)
    (m / "sources.txt").write_text("\n".join(lines) + "\n")
    (m / "configs.txt").write_text("".join(l for l in (d / "configs.txt").read_text().splitlines(True) if l.split("|")[0] in ("dft", "tx", "rx")))
PY
[ $? -eq 0 ] || exit 1
for m in "$D"/.mut/*/; do ( "$ROOT/tests/common/run_tests.sh" "$m" > "$m/out.log" 2>&1 ) & done
wait
fail=0
for m in "$D"/.mut/*/; do
  k=$(basename "$m")
  if grep -q "ALL TESTS PASSED" "$m/out.log"; then echo "$k: SURVIVED (tests did not catch it)"; fail=1; elif grep -qE "  FAIL|AssertionError" "$m/out.log" "$m"/sim_*.log 2>/dev/null; then echo "$k: killed ($(cat "$m"/sim_*.log "$m/out.log" 2>/dev/null | grep -cE '  FAIL|AssertionError') failing tests or assertions)"; else echo "$k: stopped without a test failure (build error?)"; fail=1; fi
done
[ -n "${KEEP:-}" ] || rm -rf "$D/.mut"
exit $fail
