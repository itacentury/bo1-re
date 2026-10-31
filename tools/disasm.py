#!/usr/bin/env python3
"""Disassemble PPU code with inline string/call annotations: disasm.py <addr> [count]."""
import sys

import capstone

import ppcscan
from names import load_names

idx = ppcscan.load()
elf = idx.elf
names = load_names()
md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)


def describe(target: int) -> str:
    if target in names:
        return names[target]
    try:
        s = elf.cstr(target)
        if len(s) >= 2 and s.isprintable():
            return repr(s[:60])
    except (ValueError, UnicodeDecodeError):
        pass
    return ""


def dis(start: int, count: int):
    code = elf.read(start, count * 4)
    for ins in md.disasm(code, start):
        note = ""
        if ins.mnemonic in ("bl", "b") and ins.op_str.startswith("0x"):
            note = describe(int(ins.op_str, 16)) or f"sub_{int(ins.op_str, 16):x}"
        else:
            hit = REVERSE.get(ins.address)
            if hit is not None:
                note = describe(hit) or f"[{hit:#x}]"
        label = f"\n{names[ins.address]}:" if ins.address in names and ins.address != start else ""
        if label:
            print(label)
        print(f"  {ins.address:08x}  {ins.mnemonic:8s} {ins.op_str:28s} {('; ' + note) if note else ''}")


REVERSE = {site: tgt for tgt, sites in idx.refs.items() for site in sites}

if __name__ == "__main__":
    a = int(sys.argv[1], 16)
    dis(a, int(sys.argv[2]) if len(sys.argv) > 2 else 40)
