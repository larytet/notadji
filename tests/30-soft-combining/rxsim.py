"""Helpers shared by the module 30 tests: encoded codewords, independent noise per reception, combining arithmetic."""
import math
import sys
from pathlib import Path

T = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(T / "20-ldpc-decoder"))
sys.path.insert(0, str(T / "16-tx-chain"))
sys.path.insert(0, str(T / "common"))

from dec_model import CODES, decode, words      # noqa: E402,F401
from tx_model import ldpc_encode                # noqa: E402


def encode(ci, msg):
    return ldpc_encode(ci, msg)


def reception(ci, cw, ebn0_db, rng, scale=24.0):
    """one BPSK/AWGN reception of the codeword as quantised LLRs (the demapper's scale: 24 per unit amplitude)"""
    c = CODES[ci]
    rate = c["K"] / c["N"]
    sigma = math.sqrt(1 / (2 * rate * 10 ** (ebn0_db / 10)))
    out = []
    for b in cw:
        y = (1 - 2 * b) + rng.gauss(0, sigma)
        out.append(max(-127, min(127, int(round(scale * y)))))
    return out


def combine(a, b):
    return [max(-127, min(127, x + y)) for x, y in zip(a, b)]
