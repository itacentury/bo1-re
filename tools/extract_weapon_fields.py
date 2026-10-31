#!/usr/bin/env python3
"""Dump the weapon def parse table ({name, offset, type} cspField_t entries, anchor weapon_def_fields)."""
import csv
import sys

import ppcscan
import target as targets

# Generic csParseFieldType_t codes, named from the value formats of the weapon files that use them;
# 15+ are weapon-specific types (WFT_*) with exactly one field each and are named after that field.
CSPFT = {0: "CSPFT_STRING", 4: "CSPFT_INT", 5: "CSPFT_QBOOLEAN", 6: "CSPFT_BOOL", 7: "CSPFT_FLOAT",
         8: "CSPFT_MILLISECONDS", 9: "CSPFT_FX", 10: "CSPFT_XMODEL", 11: "CSPFT_MATERIAL",
         12: "CSPFT_MATERIAL_STREAM"}


def entries(elf, a):
    while True:
        name_ptr, ofs, typ = elf.u32(a), elf.u32(a + 4), elf.u32(a + 8)
        try:
            name = elf.cstr(name_ptr)
        except ValueError:
            return
        if not (name.isprintable() and ofs < 0x10000 and typ < 0x40):
            return
        yield a, name, ofs, typ
        a += 12


def main():
    t = targets.get()
    start = t.anchor("weapon_def_fields")
    if start is None:
        print("no weapon_def_fields anchor in target.json", file=sys.stderr)
        return
    elf = ppcscan.load().elf
    type_name = lambda name, typ: CSPFT.get(typ) or (f"WFT_{name.upper()}" if typ >= 15 else "")
    rows = [{"name": name, "offset": f"0x{ofs:X}", "type": typ, "type_name": type_name(name, typ),
             "entry": f"0x{a:08X}"} for a, name, ofs, typ in entries(elf, start)]
    out = sys.argv[1] if len(sys.argv) > 1 else t.data_dir / "weapon_def_fields.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} weapon def fields", file=sys.stderr)


if __name__ == "__main__":
    main()
