#!/usr/bin/env python3
"""Upsert entries into data/<target>/{functions,globals}.csv.

  db.py func  <addr> <name> [--proto P] [--sys S] [--conf C] [--notes N]
  db.py glob  <addr> <name> [--type T] [--size N] [--sys S] [--conf C] [--notes N]
  db.py bulk  <file.tsv>     # lines: kind<TAB>addr<TAB>name<TAB>proto|type<TAB>sys<TAB>conf<TAB>notes
"""
import argparse
import csv
from pathlib import Path

import ppcscan
import target as targets

ROOT = Path(__file__).resolve().parent.parent
FUNC_FIELDS = ["addr", "opd", "name", "prototype", "subsystem", "confidence", "notes"]
GLOB_FIELDS = ["addr", "name", "type", "size", "subsystem", "confidence", "notes"]
CONFIDENCE = {"confirmed", "likely", "guess"}


def _load(path, fields):
    if not path.exists():
        return {}
    return {int(r["addr"], 16): r for r in csv.DictReader(path.open())}


def _save(path, fields, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for addr in sorted(rows):
            w.writerow({k: rows[addr].get(k, "") for k in fields})


class Db:
    def __init__(self, target=None):
        self.target = targets.get(target).name
        self.dir = targets.get(target).data_dir
        self.fpath, self.gpath = self.dir / "functions.csv", self.dir / "globals.csv"
        self.funcs = _load(self.fpath, FUNC_FIELDS)
        self.globs = _load(self.gpath, GLOB_FIELDS)
        self._opd = None

    def opd_of(self, addr):
        if self._opd is None:
            self._opd = ppcscan.load(self.target).opd
        o = self._opd.get(addr)
        return f"0x{o:08X}" if o else ""

    def func(self, addr, name, proto="", sys="", conf="likely", notes=""):
        assert conf in CONFIDENCE, conf
        old = self.funcs.get(addr, {})
        self.funcs[addr] = {"addr": f"0x{addr:08X}", "opd": self.opd_of(addr), "name": name,
                            "prototype": proto or old.get("prototype", ""), "subsystem": sys or old.get("subsystem", ""),
                            "confidence": conf, "notes": notes or old.get("notes", "")}

    def glob(self, addr, name, typ="", size="", sys="", conf="likely", notes=""):
        assert conf in CONFIDENCE, conf
        old = self.globs.get(addr, {})
        self.globs[addr] = {"addr": f"0x{addr:08X}", "name": name, "type": typ or old.get("type", ""),
                            "size": str(size) if size != "" else old.get("size", ""),
                            "subsystem": sys or old.get("subsystem", ""), "confidence": conf,
                            "notes": notes or old.get("notes", "")}

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        _save(self.fpath, FUNC_FIELDS, self.funcs)
        _save(self.gpath, GLOB_FIELDS, self.globs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["func", "glob", "bulk"])
    ap.add_argument("addr")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--proto", default="")
    ap.add_argument("--type", default="")
    ap.add_argument("--size", default="")
    ap.add_argument("--sys", default="")
    ap.add_argument("--conf", default="likely")
    ap.add_argument("--notes", default="")
    ap.add_argument("--target", default=None, help="default: $BO1_TARGET or mp")
    a = ap.parse_args()
    db = Db(a.target)
    if a.kind == "bulk":
        for line in Path(a.addr).read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            kind, addr, name, pt, sys, conf, notes = (line.split("\t") + [""] * 7)[:7]
            if kind == "func":
                db.func(int(addr, 16), name, pt, sys, conf or "likely", notes)
            else:
                typ, _, size = pt.partition(":")
                db.glob(int(addr, 16), name, typ, size, sys, conf or "likely", notes)
    elif a.kind == "func":
        db.func(int(a.addr, 16), a.name, a.proto, a.sys, a.conf, a.notes)
    else:
        db.glob(int(a.addr, 16), a.name, a.type, a.size, a.sys, a.conf, a.notes)
    db.save()


if __name__ == "__main__":
    main()
