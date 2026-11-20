"""Clock-accurate Python models of the module 22 blocks (design/22-tdd-mac.md)."""


def s(x, bits):
    x &= (1 << bits) - 1
    return x - (1 << bits) if x >> (bits - 1) else x


class Timer:
    def __init__(self):
        self.cnt = self.fno = self.fs = self.miss = self.seen = self.lost = self.serr = self.cfg = 0

    def comb(self, c):
        role, F, DL, U, UL, TA = c["role"], c["F"], c["DL"], c["U"], c["UL"], c["TA"]
        u_eff = (U - TA) & 0x1FFFFFF if role else U
        ta_ok = (not role) or TA <= U
        ul_in = ta_ok and UL != 0 and self.cnt >= u_eff and self.cnt < u_eff + UL
        dl_in = self.cnt < DL
        tx = ul_in if role else dl_in
        rx = dl_in if role else ul_in
        return dict(tx=int(tx), rx=int(rx), ul=int(ul_in))

    def step(self, c, sync):
        role, F, DL, U, UL, TA, turn = c["role"], c["F"], c["DL"], c["U"], c["UL"], c["TA"], c["turn"]
        u_eff = (U - TA) & 0x1FFFFFF if role else U
        ta_ok = (not role) or TA <= U
        dl_t = DL + turn
        if F == 0:
            bad = 1
        elif role:
            bad = int(UL != 0 and ((not ta_ok) or u_eff < dl_t))
        else:
            bad = int(U < dl_t or (UL != 0 and U + UL + turn > F))
        half = F >> 1
        d0 = self.cnt - c["SP"]
        d1 = d0 - F if d0 >= half else (d0 + F if d0 < -half else d0)
        early = self.cnt >= half and F != 0
        wrap = ((self.cnt + 1) & 0xFFFFFF) >= F
        seen0, miss0 = self.seen, self.miss
        fs = 0
        if role and sync:
            ncnt = (c["SP"] + 1) & 0xFFFFFF
            self.serr = d1
            self.miss = 0
            self.seen = 1
            self.lost = 0
            if early:
                self.fno = (self.fno + 1) & 0xFFFF
                fs = 1
        elif wrap:
            ncnt = 0
            self.fno = (self.fno + 1) & 0xFFFF
            fs = 1
            self.seen = 0
            if role:
                if seen0:
                    self.miss = 0
                else:
                    if miss0 != 15:
                        self.miss = miss0 + 1
                    if c["ML"] != 0 and ((miss0 + 1) & 15) >= c["ML"]:
                        self.lost = 1
        else:
            ncnt = self.cnt + 1
        self.cnt = ncnt
        self.fs = fs
        self.cfg = bad


class Sched:
    def __init__(self, tpu):
        self.tpu = tpu
        self.cls = 0
        self.out = dict(F=0, DL=0, U=0, UL=0, G=0)

    def update(self, rtt, turn):
        t = self.tpu
        thr0, thr1, hys = 467 * t // 10, 1001 * t // 10, 2 * t
        c = self.cls
        n = c
        if c == 0:
            if rtt > thr0 + hys:
                n = 2 if rtt > thr1 + hys else 1
        elif c == 1:
            if rtt > thr1 + hys:
                n = 2
            elif rtt + hys < thr0:
                n = 0
        else:
            if rtt + hys < thr1:
                n = 0 if rtt + hys < thr0 else 1
        f, u = {0: (1000 * t, 95 * t), 1: (2000 * t, 150 * t), 2: (4000 * t, 272 * t)}[n]
        g = rtt + 2 * turn
        us = f - u - turn
        dl = us - g if us > g else 0
        self.cls = n
        self.out = dict(F=f, DL=dl, U=us, UL=u, G=g)


def ta_next(ta, err, res, ta_max):
    t0 = ta + err
    tq = 0 if t0 <= 0 else ((t0 + res // 2) // res) * res
    return min(tq, ta_max)


class Ack:
    def __init__(self):
        self.hi = 0
        self.bits = 0
        self.have = 0
        self.late = 0
        self.fb = (0, 0, 0)   # valid, hi, bits
        self.M = (1 << 64) - 1

    def step(self, ev, fb_req):
        fb_valid = int(fb_req)
        fbhi, fbbits = self.fb[1], self.fb[2]
        if fb_req:
            fbhi, fbbits = self.hi, self.bits
        if ev is not None:
            seq, ok = ev
            diff = s(seq - self.hi, 16)
            if not self.have:
                self.have = 1
                self.hi = seq
                self.bits = ok << 63
            elif diff > 0:
                self.hi = seq
                self.bits = ((0 if diff >= 64 else self.bits >> diff) | (ok << 63)) & self.M
            elif diff < -63:
                self.late = (self.late + 1) & 0xFFFF
            elif ok:
                self.bits |= 1 << (63 + diff)
        self.fb = (fb_valid, fbhi, fbbits)


class Retx:
    def __init__(self):
        self.tab = {}                # idx -> [seq, deadline, cnt]
        self.rq, self.fq = [], []
        self.sweeping = 0
        self.pos = 0
        self.hi = self.bits = self.now_l = 0
        self.stale = self.drop = self.ovf = 0

    def outs(self):
        return dict(rtx_valid=int(bool(self.rq)), rtx_seq=self.rq[0] if self.rq else None,
                    rf_valid=int(bool(self.fq)), rf_seq=self.fq[0] if self.fq else None,
                    busy=self.sweeping, fb_ready=int(not self.sweeping))

    def step(self, cfg, sent, fb, rtx_ready, rf_ready):
        pop_r = bool(self.rq) and rtx_ready
        pop_f = bool(self.fq) and rf_ready
        rq_n_pre = len(self.rq)
        rq = list(self.rq)
        fq = list(self.fq)
        if pop_r:
            rq.pop(0)
        if pop_f:
            fq.pop(0)
        tab = {k: list(v) for k, v in self.tab.items()}          # writes go here; reads use self.tab (pre-state)
        stale, drop, ovf = self.stale, self.drop, self.ovf
        if fb is not None and not self.sweeping:
            self.hi, self.bits, self.now_l = fb[0], fb[1], cfg["now"]
            self.sweeping = 1
            self.pos = 0
        elif self.sweeping:
            seq_p = (self.hi - 63 + self.pos) & 0xFFFF
            idx = seq_p & 63
            e = self.tab.get(idx)
            here = e is not None and e[0] == seq_p
            older = s(e[0] - seq_p, 16) if e is not None else 0
            if e is not None and (here or older > 0) and not (here and (self.bits >> self.pos) & 1):
                age = s(seq_p - (self.hi - cfg["holdoff"]), 16)
                tmo = cfg["tmo"]
                timed_out = tmo != 0 and ((self.now_l - e[3]) & 0xFFFFFFFF) >= tmo
                if (here and age <= 0) or timed_out:
                    slack = s(e[1] - self.now_l, 32)
                    can = e[2] < cfg["max_retx"] and slack >= s(cfg["tx"] + cfg["owd"], 32) and rq_n_pre < 16
                    if can:
                        rq.append(e[0])
                        tab[idx][2] = (e[2] + 1) & 15
                        tab[idx][3] = self.now_l
                    else:
                        del tab[idx]
                        drop += 1
                        if len(fq) < 16:
                            fq.append(e[0])
                        else:
                            ovf += 1
            elif here:
                del tab[idx]
            elif e is not None and older < 0:
                del tab[idx]
                stale += 1
            if self.pos == 63:
                self.sweeping = 0
                self.pos = 0
            else:
                self.pos += 1
        if sent is not None:
            sq, dl = sent
            i = sq & 63
            e = self.tab.get(i)
            if e is not None and e[0] == sq:
                if i in tab:
                    tab[i][3] = cfg["now"]
            else:
                if e is not None:
                    stale += 1
                tab[i] = [sq, dl, 0, cfg["now"]]
        self.tab, self.rq, self.fq = tab, rq, fq
        self.stale, self.drop, self.ovf = stale & 0xFFFF, drop & 0xFFFF, ovf & 0xFFFF
