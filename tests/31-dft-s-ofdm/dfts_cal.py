"""Firmware-side calibration helpers of the DFT-s receive stage (design/31-dft-s-ofdm.md section 1): the MMSE gain table
and the csi of the despread symbols, from the csi of the used tones and the noise level nv (in csi units: nv = 128 sigma^2 / Es,
so that a flat channel of unit gain and SNR s has csi 128 and nv = 128 / s)."""


def make_gain_lut(nv):
    return [min(511, int(round(256 * c / (c + nv)))) if c > 0 else 0 for c in range(256)]


def csi_eff(csi_used, nv):
    """csi of the despread symbols for MMSE weighting: gamma = a / (1 - a) with a the mean gain; csi_out = gamma nv"""
    g = [c / (c + nv) if c > 0 else 0.0 for c in csi_used]
    a = sum(g) / len(g)
    if a >= 0.9999:
        return 255
    return max(0, min(255, int(round(a / (1 - a) * nv))))


def csi_eff_zf(csi_used):
    """zero forcing (table of ones): noise variance is the mean of sigma^2/|H|^2, csi_out = 128 / mean(128/csi)"""
    inv = [128.0 / c if c > 0 else 128.0 for c in csi_used]
    return max(0, min(255, int(round(128.0 / (sum(inv) / len(inv))))))
