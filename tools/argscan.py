"""Recover constant string arguments at call sites (r3..r10) via backward scan."""
from collections import Counter, defaultdict

import ppcscan

idx = ppcscan.load()
elf = idx.elf
REVERSE = {}
for tgt, sites in idx.refs.items():
    for s in sites:
        REVERSE[s] = tgt


def string_at(addr: int):
    try:
        s = elf.cstr(addr)
    except (ValueError, UnicodeDecodeError):
        return None
    return s if s and s.replace("\n", "").replace("\t", "").isprintable() else None


def call_args(site: int, window: int = 24):
    """Return {reg: value} for addi/li/ori-built constants live at a bl, scanning back to the previous call."""
    args = {}
    pc = site - 4
    done = set()
    while pc > site - window * 4:
        w = idx.words(pc, 1)[0]
        op = w >> 26
        if op == 18:  # previous branch/call ends the window
            break
        rd = (w >> 21) & 31
        ra = (w >> 16) & 31
        if op == 14 and 3 <= rd <= 10 and rd not in done:  # addi / li
            if ra == 0:
                v = w & 0xFFFF
                args[rd] = v - 0x10000 if v & 0x8000 else v
            elif pc in REVERSE:
                args[rd] = REVERSE[pc]
            done.add(rd)
        elif op == 24 and 3 <= ra <= 10 and ra not in done and pc in REVERSE:  # ori
            args[ra] = REVERSE[pc]
            done.add(ra)
        elif op in (31, 15, 32, 21, 30) and 3 <= rd <= 10 and op != 31:
            done.add(rd)
        pc -= 4
    return args


def calls_with_string_arg(reg: int = 3):
    out = defaultdict(list)
    for callee, sites in idx.calls.items():
        for s in sites:
            v = call_args(s).get(reg)
            if isinstance(v, int) and v > 0x10000:
                st = string_at(v)
                if st:
                    out[callee].append((s, st))
    return out


if __name__ == "__main__":
    res = calls_with_string_arg(3)
    for callee, lst in sorted(res.items(), key=lambda kv: -len(kv[1]))[:40]:
        print(f"{callee:#x} {len(lst):5d}  e.g. {[x[1] for x in lst[:4]]}")
