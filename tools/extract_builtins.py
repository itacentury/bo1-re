#!/usr/bin/env python3
"""Dump the static name->handler tables (GSC/CSC builtins, spawn funcs, UI script cmds, net handlers)."""
import csv
import sys

import ppcscan
import target as targets

TWO_HANDLER_TABLES = {"remote_inspect_commands"}


def entries(elf, start, stride, opd_range):
    OPD_START, OPD_END = opd_range
    a = start
    while True:
        name_ptr, opd = elf.u32(a), elf.u32(a + 4)
        if not (OPD_START <= opd < OPD_END and (opd - OPD_START) % 8 == 0):
            return
        try:
            name = elf.cstr(name_ptr)
        except ValueError:
            return
        if not name.isprintable():
            return
        third = elf.u32(a + 8) if stride >= 12 else ""
        yield a, name, opd, elf.u32(opd), third
        a += stride


def main():
    t = targets.get()
    elf = ppcscan.load().elf
    rows = []
    for start, stride, table, lookup in t.builtin_tables:
        # Most 12-byte tables end in a developer-only flag; the remote inspect table has a second handler OPD.
        two_handlers = table in TWO_HANDLER_TABLES
        for entry, name, opd, func, third in entries(elf, start, stride, t.opd):
            rows.append({"table": table, "name": name, "handler": f"0x{func:08X}", "handler_opd": f"0x{opd:08X}",
                         "developer": "" if two_handlers else third, "entry": f"0x{entry:08X}",
                         "lookup_func": f"0x{lookup:08X}" if lookup else "",
                         "handler2": f"0x{elf.u32(third):08X}" if two_handlers else ""})
    out = sys.argv[1] if len(sys.argv) > 1 else t.data_dir / "builtins.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    for t, n in Counter(r["table"] for r in rows).items():
        print(f"{t:34s} {n}", file=sys.stderr)


if __name__ == "__main__":
    main()
