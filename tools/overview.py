#!/usr/bin/env python3
"""Summarise functions in an address range: overview.py <start> <end> [--min-callers N]."""
import sys

import ppcscan
from names import load_names

idx = ppcscan.load()
elf = idx.elf
names = load_names()
callees_of = {}
for callee, sites in idx.calls.items():
    for s in sites:
        callees_of.setdefault(idx.func_of(s), set()).add(callee)
refs_of = {}
for tgt, sites in idx.refs.items():
    for s in sites:
        refs_of.setdefault(idx.func_of(s), set()).add(tgt)


def strings_in(fn, limit=4):
    out = []
    for t in sorted(refs_of.get(fn, ())):
        try:
            s = elf.cstr(t)
        except (ValueError, UnicodeDecodeError):
            continue
        if len(s) >= 3 and s.isprintable():
            out.append(s[:40])
    return out[:limit]


def label(a):
    return names.get(a, f"{a:x}")


def show(start, end, min_callers=0):
    i = __import__("bisect").bisect_left(idx.funcs, start)
    while i < len(idx.funcs) and idx.funcs[i] < end:
        fn = idx.funcs[i]
        nxt = idx.funcs[i + 1] if i + 1 < len(idx.funcs) else fn + 4
        nc = len(idx.calls.get(fn, []))
        if nc >= min_callers:
            cs = ",".join(label(c) for c in sorted(callees_of.get(fn, ()))[:6])
            print(f"{label(fn):28s} sz={nxt - fn:5x} callers={nc:4d} calls=[{cs}] str={strings_in(fn)}")
        i += 1


if __name__ == "__main__":
    mc = int(sys.argv[sys.argv.index("--min-callers") + 1]) if "--min-callers" in sys.argv else 0
    show(int(sys.argv[1], 16), int(sys.argv[2], 16), mc)
