#!/usr/bin/env python3
"""Find strings containing any of the given substrings and list referencing functions."""
import sys

import ppcscan
from names import load_names

idx = ppcscan.load()
elf = idx.elf
names = load_names()
data = elf.data


def find_all(needle: bytes):
    i = data.find(needle)
    while i != -1:
        # walk back to string start
        s = i
        while s > 0 and data[s - 1] != 0:
            s -= 1
        yield s
        i = data.find(needle, i + 1)


for needle in sys.argv[1:]:
    seen = set()
    for off in find_all(needle.encode()):
        if off in seen:
            continue
        seen.add(off)
        va = next((s.vaddr + off - s.offset for s in elf.segments if s.offset <= off < s.offset + s.filesz), None)
        if va is None:
            continue
        fns = sorted({idx.func_of(s) for s in idx.refs.get(va, [])})
        if not fns:
            continue
        text = elf.cstr(va)[:70]
        print(f"{va:#x} {text!r:74} <- {', '.join(names.get(f, f'{f:x}') for f in fns[:5])}")
