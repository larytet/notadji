"""Time-domain test signals for the synchroniser, built from the transmit-chain golden model."""
import math
import random
import sys
from pathlib import Path

import numpy as np

T = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(T / "16-tx-chain"))
from tx_model import Preamble, ofdm_symbol, mask_for, SH   # noqa: E402


def stf_ltf(l, cp_sel=1):
    """returns (stf samples with prefix, ltf1, ltf2) as numpy complex arrays"""
    pre = Preamble()
    m = mask_for(l)
    syms = []
    for kind in (0, 1, 1):
        s = pre.symbol(kind, l)
        syms.append(np.array([complex(i, q) for i, q in ofdm_symbol([(i, q) if t else (0, 0) for t, i, q in s], l, m, cp_sel)]))
    return syms


def make_burst(l, rng, snr_db, cfo_sc, gap, cp_sel=1, tail=64):
    """gap samples of noise, STF, LTF, LTF, tail of noise; carrier offset cfo_sc (in sub-carrier spacings).
    returns (int samples [(i, q)], dict of truth)"""
    n = 1 << l
    stf, l1, l2 = stf_ltf(l, cp_sel)
    sig = np.concatenate([stf, l1, l2])
    p_sig = float(np.mean(np.abs(stf) ** 2))
    sigma2 = p_sig / (10 ** (snr_db / 10))
    total = gap + len(sig) + tail
    x = np.zeros(total, complex)
    x[gap:gap + len(sig)] = sig
    k = np.arange(total)
    x = x * np.exp(2j * np.pi * cfo_sc * k / n)
    noise = (np.array([rng.gauss(0, 1) for _ in range(total)]) + 1j * np.array([rng.gauss(0, 1) for _ in range(total)])) * math.sqrt(sigma2 / 2)
    y = x + noise
    out = [(int(np.clip(round(v.real), -32768, 32767)), int(np.clip(round(v.imag), -32768, 32767))) for v in y]
    truth = dict(gap=gap, stf_len=len(stf), stf_end=gap + len(stf), ltf_len=len(l1), p_sig=p_sig, inc_true=cfo_sc / n * (1 << 24), n=n)
    return out, truth


def noise_only(l, rng, count, power):
    s = math.sqrt(power / 2)
    return [(int(np.clip(round(rng.gauss(0, s)), -32768, 32767)), int(np.clip(round(rng.gauss(0, s)), -32768, 32767))) for _ in range(count)]
