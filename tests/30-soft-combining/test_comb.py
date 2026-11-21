import os
import random

import cocotb
from cocotb.triggers import FallingEdge, Timer

from comb_model import CombModel
from stream_tb import reset, start_clock

CFG = os.environ.get("CFG", "big")
DEPTH, PEND = (8, 8) if CFG == "big" else (3, 2)
NLEN = {0: 648, 4: 1944}


def s8(v):
    return v & 0xFF


def signed8(v):
    v = int(v)
    return v - 256 if v >= 128 else v


async def setup(dut):
    for n in ("s_axis_valid", "s_axis_data", "s_axis_last", "mode", "code", "key_seq", "key_cw", "maxit",
              "res_valid", "res_ok", "drop_seq_valid", "drop_seq", "drop_all", "m_axis_ready"):
        getattr(dut, n).value = 0
    start_clock(dut.clk)
    await reset(dut)


def job(code, seq, cw, rng, mode=1, res_ok=0, amp=40, llr=None, **kw):
    n = NLEN[code]
    if llr is None:
        llr = [max(-128, min(127, int(rng.gauss(0, amp)))) for _ in range(n)]
    d = dict(code=code, seq=seq, cw=cw, mode=mode, res_ok=res_ok, llr=llr, maxit=rng.randrange(64))
    d.update(kw)
    return d


async def drive(dut, jobs, rng, pv=0.8, pr=0.8, pres=0.3, res_hold=0, max_cycles=2000000):
    """Drives the jobs; model events follow the DUT handshakes. Returns (model, stats)."""
    model = CombModel(DEPTH, PEND)
    model.outs = []
    n_exp = 0
    exp = []                 # expected output words (data, last, code, maxit)
    res_q = []               # res_ok values of fully accepted codewords, in order
    ji, beat, pre_done = 0, 0, False
    got, issued_res, cyc = 0, 0, 0
    prev = None
    total_out = sum(len(j["llr"]) for j in jobs)
    stats = dict(hit_words=0, cycles=0)
    while (got < total_out or ji < len(jobs) or res_q) and cyc < max_cycles:
        await FallingEdge(dut.clk)
        cyc += 1
        j = jobs[ji] if ji < len(jobs) else None
        # defaults
        dut.res_valid.value = 0
        dut.res_ok.value = rng.getrandbits(1)
        dut.drop_seq_valid.value = 0
        dut.drop_all.value = 0
        dut.drop_seq.value = rng.getrandbits(16)
        drop_ev = None
        drive_valid = 0
        # pre-actions of a job: wait until everything before it is finished (sync), then act in an idle cycle
        blocked = False
        if j is not None and beat == 0 and (j.get("sync") or j.get("pre")):
            idle = (not res_q) and got == n_exp
            if not idle:
                blocked = True
            elif j.get("pre") and not pre_done:
                pre = j["pre"]
                if pre[0] == "drop_seq":
                    dut.drop_seq_valid.value = 1
                    dut.drop_seq.value = pre[1]
                    drop_ev = pre[1]
                else:
                    dut.drop_all.value = 1
                    drop_ev = "all"
                pre_done = True
                blocked = True
        if j is not None and not blocked and rng.random() < pv:
            drive_valid = 1
        dut.s_axis_valid.value = drive_valid
        if j is not None and drive_valid:
            dut.s_axis_data.value = s8(j["llr"][beat])
            dut.s_axis_last.value = int(beat == len(j["llr"]) - 1)
        else:
            dut.s_axis_data.value = rng.getrandbits(8)
            dut.s_axis_last.value = rng.getrandbits(1)
        if j is not None and drive_valid and beat == 0:
            dut.mode.value = j["mode"]
            dut.code.value = j["code"]
            dut.key_seq.value = j["seq"]
            dut.key_cw.value = j["cw"]
            dut.maxit.value = j["maxit"]
        else:
            dut.mode.value = rng.getrandbits(1)          # sampled with the first LLR only
            dut.code.value = rng.choice((0, 4))
            dut.key_seq.value = rng.getrandbits(16)
            dut.key_cw.value = rng.getrandbits(8)
            dut.maxit.value = rng.getrandbits(6)
        res_now = None
        if res_q and cyc >= res_hold and rng.random() < pres:
            res_now = res_q[0]
            dut.res_valid.value = 1
            dut.res_ok.value = res_now
        dut.m_axis_ready.value = int(rng.random() < pr)
        await Timer(1, unit="ns")
        ready = int(dut.s_axis_ready.value)
        mv, mr = int(dut.m_axis_valid.value), int(dut.m_axis_ready.value)
        md, ml = signed8(dut.m_axis_data.value), int(dut.m_axis_last.value)
        mc, mi = int(dut.m_code.value), int(dut.m_maxit.value)
        # protocol: output stable while valid and not ready
        if prev is not None and prev[0] and not prev[1]:
            assert mv and (md, ml) == prev[2], "output changed while stalled"
        prev = (mv, mr, (md, ml))
        # model events in the order of the RTL: first LLR, result, drop
        if drive_valid and ready:
            if beat == 0:
                out = model.first(j["mode"], j["seq"], j["cw"], j["code"], j["llr"])
                model.outs.append(out)
                n_exp += len(out)
                exp.extend((v, int(i == len(out) - 1), j["code"], j["maxit"]) for i, v in enumerate(out))
            beat += 1
            if beat == len(j["llr"]):
                res_q.append(j["res_ok"])
                ji += 1
                beat = 0
                pre_done = False
        if res_now is not None:
            model.res(res_now)
            res_q.pop(0)
            issued_res += 1
        if drop_ev is not None:
            model.drop(None if drop_ev == "all" else drop_ev)
        if mv and mr:
            assert got < len(exp), "output word without expectation"
            e = exp[got]
            assert (md, ml, mc, mi) == e, f"word {got}: got {(md, ml, mc, mi)} expected {e}"
            got += 1
    assert got == total_out, f"only {got} of {total_out} words"
    for _ in range(4):
        await FallingEdge(dut.clk)
    return model, cyc


def check_counters(dut, model):
    assert int(dut.n_hit.value) == model.n_hit, (int(dut.n_hit.value), model.n_hit)
    assert int(dut.n_miss.value) == model.n_miss, (int(dut.n_miss.value), model.n_miss)
    assert int(dut.n_evict.value) == model.n_evict, (int(dut.n_evict.value), model.n_evict)
    assert int(dut.occupancy.value) == model.occupancy(), (int(dut.occupancy.value), model.occupancy())


@cocotb.test()
async def t30_01_random(dut):
    """T30-01 bit-exact against the model: random keys, results, bypass, random valid and ready"""
    await setup(dut)
    rng = random.Random(3001)
    jobs = []
    for _ in range(60 if CFG == "big" else 40):
        code = 4 if rng.random() < 0.25 else 0
        j = job(code, rng.randrange(4), rng.randrange(2), rng, mode=0 if rng.random() < 0.1 else 1,
                res_ok=int(rng.random() < 0.3))
        jobs.append(j)
    # a few with the same key and the same LLR vector (true retransmissions)
    base = job(0, 9, 1, rng)
    jobs += [dict(base, mode=1, res_ok=0, maxit=3), dict(base, maxit=5, res_ok=1), dict(base, maxit=7)]
    model, cyc = await drive(dut, jobs, rng, pv=0.85, pr=0.8, pres=0.25)
    check_counters(dut, model)
    dut._log.info(f"hits {model.n_hit} misses {model.n_miss} evictions {model.n_evict} cycles {cyc}")
    assert model.n_hit >= 5 and model.n_miss >= 5
    if CFG == "small":
        assert model.n_evict >= 1, "no eviction exercised"


@cocotb.test()
async def t30_02_policy(dut):
    """T30-02 directed policy: failure keeps, success frees, drop, code mismatch, replacement, back-pressure"""
    await setup(dut)
    rng = random.Random(3002)
    a = job(0, 1, 0, rng)
    b = job(0, 1, 0, rng)       # same key, other LLRs
    c = job(0, 1, 0, rng)
    jobs = [
        dict(a, res_ok=0, sync=True),                 # miss, fails: stays
        dict(b, res_ok=1, sync=True),                 # hit: a + b, decodes: freed
        dict(c, res_ok=0, sync=True),                 # miss again (freed)
        dict(job(4, 1, 0, rng, llr=c["llr"][:1] * 1944), res_ok=0, sync=True),     # other code, same key: miss
        dict(job(0, 2, 5, rng), res_ok=0, sync=True),                       # second entry
        dict(job(0, 2, 6, rng), res_ok=0, sync=True, pre=("drop_seq", 1)),  # drops seq 1 (both codes) first
        dict(job(0, 1, 0, rng), res_ok=0, sync=True),                       # miss: dropped
        dict(job(0, 2, 5, rng), res_ok=0, sync=True, pre=("all",)),         # drop_all, then miss
    ]
    model, cyc = await drive(dut, jobs, rng, pv=1.0, pr=1.0, pres=1.0)
    check_counters(dut, model)
    assert model.n_hit == 1, model.n_hit
    if CFG == "small":
        # DEPTH 3: five failing codewords of different keys -> replacement of the oldest, then PEND 2 stall
        js = [job(0, 20 + i, 0, rng, res_ok=0) for i in range(5)]
        js += [dict(js[0], res_ok=0), dict(js[4], res_ok=0)]      # key 0 was replaced (miss), key 4 retained (hit)
        model, cyc = await drive(dut, js, rng, pv=1.0, pr=1.0, pres=1.0, res_hold=0)
        assert model.n_evict >= 2, model.n_evict
        # back-pressure: no results for a while, PEND = 2: the third first-LLR stalls
        ovf0 = int(dut.n_ovf.value)
        js = [job(0, 40 + i, 0, rng, res_ok=1) for i in range(5)]
        model, cyc = await drive(dut, js, rng, pv=1.0, pr=1.0, pres=1.0, res_hold=3000 + 0)
        assert int(dut.n_ovf.value) > ovf0, "pending-FIFO stall not exercised"


@cocotb.test()
async def t30_03_saturation(dut):
    """T30-03 saturation at +/-127, -128 clamped, three receptions"""
    await setup(dut)
    rng = random.Random(3003)
    n = 648
    hi = [127] * n
    lo = [-128] * n
    mix = [(-127 if i % 3 == 0 else (127 if i % 3 == 1 else 5)) for i in range(n)]
    jobs = [job(0, 7, 3, rng, llr=hi, res_ok=0, sync=True),
            job(0, 7, 3, rng, llr=hi, res_ok=0, sync=True),          # 254 -> 127
            job(0, 7, 3, rng, llr=lo, res_ok=0, sync=True),          # 127 + (-127) = 0
            job(0, 7, 3, rng, llr=mix, res_ok=0, sync=True),         # 0 + mix
            job(0, 7, 3, rng, llr=lo, res_ok=0, sync=True)]
    model, cyc = await drive(dut, jobs, rng, pv=0.9, pr=0.9, pres=0.9)
    check_counters(dut, model)
    # independent check of the arithmetic of the chain
    o = model.outs
    assert o[0] == [127] * n and o[1] == [127] * n and o[2] == [0] * n          # independent expectations
    assert o[3] == mix
    assert o[4] == [max(-127, min(127, m - 127)) for m in mix]
