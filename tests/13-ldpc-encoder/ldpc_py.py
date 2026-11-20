"""Python side of the LDPC tests: parity-check matrices from the generated base matrices and from the AFF3CT alist."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODES = json.loads((HERE / "ldpc_codes.json").read_text())
ALIST = HERE / "data" / "WIFI_540_648.alist"


def h_rows(code):
    """list of ints, one per parity check, bit c set when column c participates"""
    z, mb = code["Z"], code["mb"]
    rows = []
    for i in range(mb):
        for r in range(z):
            m = 0
            for j in range(24):
                s = code["base"][i][j]
                if s is not None:
                    m |= 1 << (j * z + ((r + s) % z))
            rows.append(m)
    return rows


def alist_rows(path=ALIST):
    t = Path(path).read_text().split("\n")
    n, m = map(int, t[0].split())
    rows = [0] * m
    for j in range(n):
        for x in t[4 + j].split():
            if int(x) > 0:
                rows[int(x) - 1] |= 1 << j
    return n, rows


def check(rows, cw):
    return all(bin(r & cw).count("1") % 2 == 0 for r in rows)


def to_words(value, nbits):
    n = (nbits + 31) // 32
    return [(value >> (32 * i)) & 0xFFFFFFFF for i in range(n)]


def from_words(words):
    v = 0
    for i, w in enumerate(words):
        v |= w << (32 * i)
    return v
