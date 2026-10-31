"""Call-site argument recovery on top of ppcsim.step()."""
import ppcscan
from ppcsim import M64, s32, sext16, step, float_reader  # noqa: F401  (re-exported)


class Sim:
    def __init__(self, idx: ppcscan.Index):
        self.idx = idx
        self.elf = idx.elf
        self.read_float = float_reader(idx.elf)

    def run(self, start, end, snapshots=()):
        """Simulate [start, end); return (gpr, fpr) at `end`, or {pc: (gpr, fpr)} if snapshots given."""
        g, f, snaps, want = {}, {}, {}, set(snapshots)
        toc = self.elf.toc
        words = self.idx.words(start, (end - start) // 4)
        for i, w in enumerate(words):
            pc = start + i * 4
            if pc in want:
                snaps[pc] = (dict(g), dict(f))
            step(g, f, pc, w, toc, self.read_float)
        return snaps if want else (g, f)

    def states_at(self, sites):
        """Simulate each containing function once and return {site: (gpr, fpr)}."""
        by_func = {}
        for s in sites:
            by_func.setdefault(self.idx.func_of(s), []).append(s)
        out = {}
        for fn, ss in by_func.items():
            out.update(self.run(fn, max(ss) + 4, ss))
        return out

    def stored_result(self, site, gpr, look=24):
        """Address where the call's r3 result is stored (stw r3, d(rX)) before the next call."""
        g = {k: v for k, v in gpr.items() if k >= 13}
        f = {}
        res = {3}
        toc = self.elf.toc
        for pc in range(site + 4, site + 4 + look * 4, 4):
            w = self.idx.words(pc, 1)[0]
            op = w >> 26
            rd, ra, rb, imm = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0xFFFF
            if op == 36 and rd in res:
                return (g[ra] + sext16(imm)) & 0xFFFFFFFF if ra in g and ra != 2 else None
            if op == 31 and (w >> 1) & 0x3FF == 444 and rd == rb and rd in res:
                res.add(ra)
                continue
            if op in (18, 16, 19):
                break
            step(g, f, pc, w, toc)
            for r in list(res):
                # result register overwritten by something else
                if r != 3 and r in g:
                    res.discard(r)
        return None
