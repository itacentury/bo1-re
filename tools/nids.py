#!/usr/bin/env python3
"""Resolve PS3 import NIDs by hashing candidate names; only exact hash matches are accepted."""
import argparse
import csv
import hashlib
import re
import struct
import sys
from pathlib import Path

from ps3elf import Ps3Elf

NID_SUFFIX = bytes.fromhex("6759659904250490566427499489741a")


def nid(name: str) -> int:
    return struct.unpack("<I", hashlib.sha1(name.encode() + NID_SUFFIX).digest()[:4])[0]


def load_candidates(paths):
    """Accept plain name lists and RPCS3-style REG_FUNC/REG_FNID sources."""
    hashed, explicit = set(), {}
    for p in paths:
        text = Path(p).read_text(errors="ignore")
        for m in re.finditer(r"REG_FNID\(\s*\w+\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*(\w+)", text):
            explicit[int(m.group(1), 16)] = m.group(2)
        hashed.update(re.findall(r"REG_(?:FUNC|VAR)\(\s*\w+\s*,\s*(\w+)", text))
        if p.endswith(".txt"):
            hashed.update(line.strip() for line in text.splitlines() if line.strip())
    table = {nid(n): n for n in hashed}
    table.update(explicit)
    return table


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("elf")
    ap.add_argument("out_csv")
    ap.add_argument("sources", nargs="+", help="name lists (*.txt) or RPCS3 module sources")
    args = ap.parse_args()

    table = load_candidates(args.sources)
    elf = Ps3Elf(args.elf)
    rows, unresolved = [], 0
    for lib, idx, value, slot in elf.imports():
        name = table.get(value, "")
        unresolved += not name
        # The stub slot initially holds the address of the .sceStub.text trampoline.
        rows.append({"library": lib, "index": idx, "nid": f"0x{value:08X}", "name": name,
                     "stub_slot": f"0x{slot:08X}", "stub_code": f"0x{elf.u32(slot):08X}"})
    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} imports, {len(rows) - unresolved} resolved, {unresolved} unresolved", file=sys.stderr)


if __name__ == "__main__":
    main()
