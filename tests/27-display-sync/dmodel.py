"""Cycle-accurate Python models of the module 27 blocks."""


def s(x, bits):
    x &= (1 << bits) - 1
    return x - (1 << bits) if x >> (bits - 1) else x


class Timing:
    def __init__(self):
        self.hx = self.vy = 0
        self.slip_l = 0
        self.fc = 0

    @staticmethod
    def tot(c):
        return c["h_active"] + c["h_fp"] + c["h_sync"] + c["h_bp"], c["v_active"] + c["v_fp"] + c["v_sync"] + c["v_bp"]

    def comb(self, c):
        hs_lo = c["h_active"] + c["h_fp"]
        hs_hi = hs_lo + c["h_sync"]
        vs_lo = c["v_active"] + c["v_fp"]
        vs_hi = vs_lo + c["v_sync"]
        in_hs = hs_lo <= self.hx < hs_hi
        in_vs = vs_lo <= self.vy < vs_hi
        en = c["en"]
        return dict(hs=int(en and (in_hs if c["hs_pol"] else not in_hs)), vs=int(en and (in_vs if c["vs_pol"] else not in_vs)),
                    de=int(en and self.hx < c["h_active"] and self.vy < c["v_active"]), x=self.hx, y=self.vy,
                    ls=int(en and self.hx == 0), vss=int(en and self.hx == 0 and self.vy == vs_lo), fc=self.fc)

    def step(self, c):
        if not c["en"]:
            self.hx = self.vy = self.slip_l = self.fc = 0
            return
        ht, vt = self.tot(c)
        if self.hx == 0 and self.vy == 0:
            self.slip_l = s(c["slip"], 8)
        slip_line = self.vy == c["v_active"]
        smin = -c["h_bp"] + 1
        eff = max(self.slip_l, smin)
        hlast = ht - 1 + (eff if slip_line else 0)
        if self.hx == hlast:
            self.hx = 0
            if self.vy == vt - 1:
                self.vy = 0
                self.fc = (self.fc + 1) & 0xFFFF
            else:
                self.vy += 1
        else:
            self.hx = (self.hx + 1) & 0xFFFF


class Phase:
    def __init__(self):
        self.c = 0
        self.silent = 0
        self.err = 0
        self.valid = 0
        self.lost = 1

    def step(self, period, target, rx_fs, disp_vs):
        d0 = self.c - target
        hp = period >> 1
        d1 = d0 - period if d0 >= hp else (d0 + period if d0 < -hp else d0)
        valid = 0
        if rx_fs:
            c = 0
            self.silent = 0
            self.lost = 0
        else:
            c = 0 if (period != 0 and self.c + 1 >= period) else (self.c + 1) & 0xFFFFFF
            if (self.silent >> 1) >= period:
                self.lost = 1
            else:
                self.silent += 1
        self.c = c
        if disp_vs and period != 0:
            self.err = s(d1, 24)
            valid = 1
        self.valid = valid


class PI:
    def __init__(self):
        self.acc = 0
        self.ctl = 0
        self.valid = 0

    def step(self, en, hold, err_valid, err, kp, ki, ppm_max, slew_max, preset_valid, preset):
        if not en:
            self.acc = self.ctl = self.valid = 0
            return
        self.valid = 0
        lim = ppm_max << 24
        if preset_valid:
            pc = max(-ppm_max, min(ppm_max, preset))
            self.acc = pc << 24
            self.ctl = pc
        elif err_valid and not hold:
            raw = self.acc + err * ki
            acc_n = max(-lim, min(lim, raw))
            p = (err * kp) >> 16
            i = acc_n >> 24
            u = max(-ppm_max, min(ppm_max, p + i))
            d = u - self.ctl
            un = self.ctl + slew_max if d > slew_max else (self.ctl - slew_max if d < -slew_max else u)
            self.acc = acc_n
            self.ctl = s(un, 16)
            self.valid = 1


class Lines:
    def __init__(self):
        self.fresh = set()
        self.cur_buf = 0
        self.stale_run = self.cur_run = 0
        self.scanned = 0
        self.stale = self.cur = self.late = 0
        self.use_cur = self.buf_sel = self.rd_valid = 0

    def step(self, swap, wr_valid, wr_line, wr_n, rd_req, rd_line):
        self.rd_valid = 0
        if swap:
            self.cur_buf ^= 1
            self.fresh = set()
            self.stale, self.cur = self.stale_run, self.cur_run
            self.stale_run = self.cur_run = 0
            self.scanned = 0
            return
        old = set(self.fresh)
        old_scanned = self.scanned
        if wr_valid:
            for i in range(wr_line, min(2048, wr_line + wr_n)):
                self.fresh.add(i)
            if wr_line < old_scanned:
                self.late = (self.late + 1) & 0xFFFF
        if rd_req:
            f = rd_line in old
            self.use_cur = int(f)
            self.buf_sel = self.cur_buf if f else self.cur_buf ^ 1
            self.rd_valid = 1
            if f:
                self.cur_run += 1
            else:
                self.stale_run += 1
            if rd_line + 1 > self.scanned:
                self.scanned = rd_line + 1
