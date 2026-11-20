"""Behavioural stand-in for the hard encoder: Annex-B output with slices whose sizes follow the rate-control target (an assumption)."""
import random


def emu_prevent(payload):
    out, zeros = [], 0
    for b in payload:
        if zeros >= 2 and b <= 3:
            out.append(3)
            zeros = 0
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    if out and out[-1] == 0:
        out.append(3)
    return out


HDR = {
    0: dict(aud=[0x09], sps=[0x67], pps=[0x68], sei=[0x06], slice=lambda ref: [0x41 | (ref << 5 & 0x60) & 0x60 | 0x01 if False else 0x41], idr=[0x65]),
    1: dict(aud=[0x46, 0x01], sps=[0x42, 0x01], pps=[0x44, 0x01], sei=[0x4E, 0x01], slice=lambda ref: [0x02, 0x01], idr=[0x26, 0x01]),
}


def nal_type_of(codec, header0):
    return (header0 & 0x1F) if codec == 0 else (header0 >> 1) & 0x3F


def make_nal(codec, kind, rng, n_payload, ref=2):
    h = HDR[codec][kind] if kind != "slice" else HDR[codec]["slice"](ref)
    payload = [rng.choice([0, 0, 0, 1, 2, 3, rng.randint(4, 255)]) if rng.random() < 0.15 else rng.randint(4, 255) for _ in range(max(0, n_payload))]
    return list(h) + emu_prevent(payload)


def wrap_nal(nal, rng):
    start = [0, 0, 1] if rng.random() < 0.5 else [0, 0, 0, 1]
    trail = [0] * (rng.choice([0, 0, 1, 2]))
    return start + nal + trail


def frame_bytes(codec, rng, frame_no, S, sizes, idr=False, with_aud=True, ps_every_idr=True):
    """returns (stream bytes, list of (kind, nal bytes)) for one frame; sizes: NAL payload sizes in bytes per slice"""
    nals = []
    if with_aud:
        nals.append(("aud", make_nal(codec, "aud", rng, 1)))
    if idr and ps_every_idr:
        nals.append(("sps", make_nal(codec, "sps", rng, 12)))
        nals.append(("pps", make_nal(codec, "pps", rng, 5)))
    if rng.random() < 0.1:
        nals.append(("sei", make_nal(codec, "sei", rng, 9)))
    for i in range(S):
        nals.append(("idr" if idr else "slice", make_nal(codec, "idr" if idr else "slice", rng, sizes[i])))
    stream = []
    for k, n in nals:
        stream += wrap_nal(n, rng)
    return stream, nals
