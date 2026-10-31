#!/usr/bin/env python3
"""Check every database entry against the ELF; exit 1 on errors."""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import ppcscan
from nids import nid

import target as targets

ROOT = Path(__file__).resolve().parent.parent
CONF = {"confirmed", "likely", "guess"}


def main(target=None):
    t = targets.get(target)
    idx = ppcscan.load(t.name)
    TEXT, STUB = t.text, t.stub
    rw = next(s for s in idx.elf.segments if s.flags & 2)
    WRITABLE = (rw.vaddr, rw.vaddr + rw.memsz)
    starts = set(idx.funcs)
    data = t.data_dir
    errors, warnings = [], []
    rows = lambda f: list(csv.DictReader((data / f).open())) if (data / f).exists() else []
    hexa = lambda v: int(v, 16)

    funcs = rows("functions.csv")
    for name, n in Counter(r["name"] for r in funcs).items():
        if n > 1:
            errors.append(f"functions.csv: duplicate name {name}")
    for r in funcs:
        a = hexa(r["addr"])
        if not (TEXT[0] <= a < TEXT[1]) or a & 3:
            errors.append(f"functions.csv: {r['name']} {a:#x} not an aligned .text address")
        elif a not in starts:
            warnings.append(f"functions.csv: {r['name']} {a:#x} is not a known function start")
        if r["opd"] and idx.elf.u32(hexa(r["opd"])) != a:
            errors.append(f"functions.csv: {r['name']} opd {r['opd']} does not point to {a:#x}")
        if r["confidence"] not in CONF:
            errors.append(f"functions.csv: {r['name']} bad confidence {r['confidence']!r}")
        if r["prototype"] and r["name"] + "(" not in r["prototype"].replace(" (", "("):
            errors.append(f"functions.csv: {r['name']} prototype does not name the function")

    for r in rows("globals.csv"):
        a = hexa(r["addr"])
        if not (WRITABLE[0] <= a < WRITABLE[1]):
            errors.append(f"globals.csv: {r['name']} {a:#x} outside the RW segment")
        if r["confidence"] not in CONF:
            errors.append(f"globals.csv: {r['name']} bad confidence")

    for r in rows("imports.csv"):
        if not r["name"] or nid(r["name"]) != hexa(r["nid"]):
            # REG_FNID names come with explicit NIDs and need not hash to them
            warnings.append(f"imports.csv: {r['library']}::{r['name']} does not hash to {r['nid']}")
        if not (STUB[0] <= hexa(r["stub_code"]) < STUB[1]):
            errors.append(f"imports.csv: {r['name']} stub outside .sceStub.text")

    for f, col in (("commands.csv", "handler"), ("builtins.csv", "handler"), ("builtins.csv", "handler2")):
        for r in rows(f):
            if r.get(col) and hexa(r[col]) not in starts:
                errors.append(f"{f}: {r['name']} handler {r[col]} is not a function start")

    # Optional files derived from the PC rawfiles (tools/raw_extract.py) must name known builtins.
    builtin_names = {r["name"].lower() for r in rows("builtins.csv")}
    for r in rows("builtins_script.csv"):
        if r["name"] not in builtin_names:
            errors.append(f"builtins_script.csv: {r['name']} is not in builtins.csv (rerun raw_extract.py builtins)")

    for r in rows("dvars.csv"):
        if r["dvar_ptr"] and not (WRITABLE[0] <= hexa(r["dvar_ptr"]) < WRITABLE[1]):
            errors.append(f"dvars.csv: {r['name']} dvar_ptr outside RW segment")

    structs = json.loads((data / "structs.json").read_text()) if (data / "structs.json").exists() else {}
    for sname, s in structs.items():
        if sname.startswith("_"):
            continue
        size = int(s["size"], 16) if s.get("size") else None
        for fld in s["fields"]:
            if size and int(fld["offset"], 16) >= size:
                errors.append(f"structs.json: {sname}.{fld['name']} offset beyond size")
            if fld["confidence"] not in CONF:
                errors.append(f"structs.json: {sname}.{fld['name']} bad confidence")

    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
