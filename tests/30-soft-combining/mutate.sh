#!/bin/bash
# M-30: mutation checks of llr_combiner. Each mutant must make at least one test fail. Usage: source scripts/sim_env.sh; tests/30-soft-combining/mutate.sh
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
D="$ROOT/tests/30-soft-combining"
rm -rf "$D/.mut"; mkdir -p "$D/.mut"
python3 - "$ROOT" "$D" <<'PY'
import sys
from pathlib import Path
root, d = Path(sys.argv[1]), Path(sys.argv[2])
src = (root / "rtl/30-soft-combining/llr_combiner.sv").read_text()
M = {
    "a_no_saturation": ("if (v > 9'sd127) sat127 = 8'sd127;", "if (1'b0) sat127 = 8'sd127;"),
    "b_never_free": ("v_nx[ps] = 1'b0;", ";"),
    "c_key_ignores_cw": ("seq_q[i] == key_seq && cw_q[i] == key_cw && cd_q[i] == code", "seq_q[i] == key_seq && cd_q[i] == code"),
    "d_drop_seq_ignored": ("if (sq_nx[i] == drop_seq) v_nx[i] = 1'b0;", ";"),
    "e_victim_lowest_index": ("if (i == 0 || age > maxage) begin", "if (i == 0) begin"),
    "f_hit_not_added": ("wire signed [7:0] comb_v = a_hit ? sat127(9'(a_data_c) + 9'(rdata)) : a_data_c;", "wire signed [7:0] comb_v = a_data_c;"),
    "g_result_ok_ignored": ("if (res_ok && v1[ps]", "if (v1[ps]"),
}
for k, (old, new) in M.items():
    assert src.count(old) == 1, f"mutation {k}: pattern found {src.count(old)} times"
    m = d / ".mut" / k
    m.mkdir(parents=True)
    (m / "llr_combiner.sv").write_text(src.replace(old, new))
    for f in ("test_comb.py", "comb_model.py", "rxsim.py"):
        (m / f).write_text((d / f).read_text())
    (m / "configs.txt").write_text("".join(l for l in (d / "configs.txt").read_text().splitlines(True) if l.startswith("comb")))
    (m / "sources.txt").write_text(f"tests/30-soft-combining/.mut/{k}/llr_combiner.sv\n")
PY
[ $? -eq 0 ] || exit 1
for m in "$D"/.mut/*/; do ( "$ROOT/tests/common/run_tests.sh" "$m" > "$m/out.log" 2>&1 ) & done
wait
fail=0
for m in "$D"/.mut/*/; do
  k=$(basename "$m")
  if grep -q "ALL TESTS PASSED" "$m/out.log"; then echo "$k: SURVIVED (tests did not catch it)"; fail=1; else echo "$k: killed ($(grep -c '  FAIL' "$m/out.log") failing tests)"; fi
done
rm -rf "$D/.mut"
exit $fail
