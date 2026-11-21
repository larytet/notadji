"""Reference model of llr_combiner (design/30-soft-combining.md section 2).
Events of one clock are applied in the order: first LLR accepted, decoder result, drop."""


def sat127(v):
    return max(-127, min(127, v))


class CombModel:
    def __init__(self, depth=8, pend=8):
        self.depth, self.pend_max = depth, pend
        self.slots = [None] * depth          # dict(seq, cw, code, stamp, data) or None
        self.alloc = 0
        self.pend = []                       # (used, slot, seq, cw, code)
        self.n_hit = self.n_miss = self.n_evict = 0

    def first(self, mode, seq, cw, code, llr):
        """first LLR of a codeword accepted: returns the combined LLR vector the DUT must output"""
        x = [max(-127, v) for v in llr]                          # -128 is outside the LLR range
        if not mode:
            self.pend.append((0, 0, seq, cw, code))
            return x
        found = None
        for i, s in enumerate(self.slots):
            if s and s["seq"] == seq and s["cw"] == cw and s["code"] == code:
                found = i
                break
        if found is not None:
            old = self.slots[found]["data"]
            assert len(old) == len(x), "same key with different length"
            out = [sat127(a + b) for a, b in zip(x, old)]
            self.n_hit += 1
            self.slots[found]["data"] = out
            slot = found
        else:
            self.n_miss += 1
            free = [i for i, s in enumerate(self.slots) if s is None]
            if free:
                slot = free[0]
            else:
                ages = [(self.alloc - s["stamp"]) & 0xFFFF for s in self.slots]
                slot = ages.index(max(ages))
                self.n_evict += 1
            out = x
            self.slots[slot] = dict(seq=seq, cw=cw, code=code, stamp=self.alloc, data=out)
            self.alloc = (self.alloc + 1) & 0xFFFF
        self.pend.append((1, slot, seq, cw, code))
        return out

    def res(self, ok):
        if not self.pend:
            return
        used, slot, seq, cw, code = self.pend.pop(0)
        s = self.slots[slot]
        if used and ok and s and s["seq"] == seq and s["cw"] == cw and s["code"] == code:
            self.slots[slot] = None

    def drop(self, seq=None):
        for i, s in enumerate(self.slots):
            if s and (seq is None or s["seq"] == seq):
                self.slots[i] = None

    def occupancy(self):
        return sum(1 for s in self.slots if s)
