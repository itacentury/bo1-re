"""Fast reference/call scanner for PS3 PPU code (no full disassembly).

Runs ppcsim.step() linearly over .text (state resets at each function start) and
records every resolved absolute reference plus every `bl` call edge.
"""
import bisect
import pickle
import struct
from collections import defaultdict
from pathlib import Path

import target as targets
from ppcsim import step
from ps3elf import Ps3Elf

ROOT = targets.ROOT


class Index:
    def __init__(self, elf: Ps3Elf, target: targets.Target):
        self.elf = elf
        self.target = target.name
        self.opd = {}         # func addr -> opd addr
        self.refs = defaultdict(list)   # target -> [insn addr]
        self.calls = defaultdict(list)  # callee -> [callsite]
        self.funcs = []       # sorted function starts

    def build(self):
        e = self.elf
        t = targets.get(self.target)
        TEXT_START, TEXT_END = t.text
        for opd, func, _ in e.opd_entries(*t.opd):
            self.opd[func] = opd
        starts = set(self.opd)
        code = e.read(TEXT_START, TEXT_END - TEXT_START)
        words = struct.unpack(f">{len(code) // 4}I", code)
        # First pass: collect bl targets as additional function starts.
        for i, w in enumerate(words):
            if w >> 26 == 18 and w & 3 == 1:
                li = w & 0x03FFFFFC
                if li & 0x02000000:
                    li -= 0x04000000
                pc = TEXT_START + i * 4
                tgt = (pc + li) & 0xFFFFFFFF
                self.calls[tgt].append(pc)
                starts.add(tgt)
        extra = t.data_dir / "ghidra_functions.txt"
        if extra.exists():
            starts.update(int(l, 16) for l in extra.read_text().split() if l.startswith("0x"))
        self.funcs = sorted(s for s in starts if TEXT_START <= s < TEXT_END)
        fstart = set(self.funcs)
        toc = e.toc
        g, f = {}, {}
        for i, w in enumerate(words):
            pc = TEXT_START + i * 4
            if pc in fstart:
                g.clear()
            ref = step(g, f, pc, w, toc)
            if ref is not None and 0x10000 <= ref < 0x30000000:
                self.refs[ref].append(pc)
        return self

    def func_of(self, addr: int):
        i = bisect.bisect_right(self.funcs, addr) - 1
        return self.funcs[i] if i >= 0 else None

    def words(self, start: int, count: int):
        return struct.unpack(f">{count}I", self.elf.read(start, count * 4))


def load(target: str = None) -> Index:
    t = targets.get(target)
    cp = ROOT / f"build/index_{t.name}.pkl"
    deps = [t.elf_path, t.data_dir / "target.json", t.data_dir / "ghidra_functions.txt",
            Path(__file__).parent / "ppcscan.py", Path(__file__).parent / "ppcsim.py"]
    if cp.exists() and all(cp.stat().st_mtime > d.stat().st_mtime for d in deps if d.exists()):
        idx = pickle.loads(cp.read_bytes())
        idx.elf = Ps3Elf(t.elf_path)
        return idx
    idx = Index(Ps3Elf(t.elf_path), t).build()
    elf, idx.elf = idx.elf, None
    cp.write_bytes(pickle.dumps(idx))
    idx.elf = elf
    return idx
