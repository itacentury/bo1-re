#!/usr/bin/env python3
"""Match functions between two targets (default mp -> sp_zm) and write data/cross/<a>_<b>.csv.

Passes (each only pairs functions that are still unmatched on both sides):
  1. name     - same handler name in builtins.csv / commands.csv, or lookup function of a
                same-named table (both targets extracted)
  2. exact    - identical normalised code (absolute addresses and branch targets masked), unique
  3. strings  - identical set of referenced strings, unique on both sides
  4. callees  - for matched pairs, callees at the same call-site position with equal size class,
                repeated until nothing changes
"""
import argparse
import csv
import hashlib
from collections import Counter, defaultdict

import ppcscan
import target as targets

MIN_WORDS = 8          # shorter functions are too generic for exact/strings matching
MAX_WORDS = 0x4000


class Side:
    def __init__(self, name):
        self.name = name
        self.idx = ppcscan.load(name)
        self.t = targets.get(name)
        idx = self.idx
        self.ref_pcs = {pc: tgt for tgt, pcs in idx.refs.items() for pc in pcs}
        self.size = {}
        nxt = dict(zip(idx.funcs, idx.funcs[1:] + [self.t.text[1]]))
        for f in idx.funcs:
            self.size[f] = min((nxt[f] - f) // 4, MAX_WORDS)
        self.callees = defaultdict(list)   # func -> callees in call-site order
        for callee, sites in idx.calls.items():
            for s in sites:
                self.callees[idx.func_of(s)].append((s, callee))
        for f in self.callees:
            self.callees[f] = [c for _, c in sorted(self.callees[f])]
        self.strings = defaultdict(set)
        for pc, tgt in self.ref_pcs.items():
            s = self._string(tgt)
            if s:
                self.strings[idx.func_of(pc)].add(s)

    def _string(self, va):
        try:
            s = self.idx.elf.cstr(va)
        except (ValueError, UnicodeDecodeError):
            return None
        return s if len(s) >= 4 and s.replace("\n", "").isprintable() else None

    def fingerprint(self, f):
        n = self.size[f]
        words = self.idx.words(f, n)
        out = []
        for i, w in enumerate(words):
            op = w >> 26
            pc = f + i * 4
            if op == 18:                       # b/bl: target differs between binaries
                w &= 0xFC000003
            elif op == 15 or pc in self.ref_pcs or (32 <= op <= 55 and (w >> 16) & 31 == 2):
                w &= 0xFFFF0000                # lis / absolute ref / TOC-relative: mask immediate
            out.append(w)
        return hashlib.sha1(b"".join(x.to_bytes(4, "big") for x in out)).digest()


def unique_by(keyfn, funcs):
    groups = defaultdict(list)
    for f in funcs:
        k = keyfn(f)
        if k is not None:
            groups[k].append(f)
    return {k: v[0] for k, v in groups.items() if len(v) == 1}


def named_handlers(t):
    out = {}
    for fname, key in (("builtins.csv", "table"), ("commands.csv", "kind")):
        p = t.data_dir / fname
        if not p.exists():
            continue
        for r in csv.DictReader(p.open()):
            if r["handler"]:
                out.setdefault((r[key], r["name"]), set()).add(int(r["handler"], 16))
            if r.get("lookup_func"):
                out.setdefault(("lookup", r["table"]), set()).add(int(r["lookup_func"], 16))
    return {k: next(iter(v)) for k, v in out.items() if len(v) == 1}


def match(a: Side, b: Side):
    pairs = {}          # a func -> (b func, method)
    used_b = set()

    def add(fa, fb, method):
        if fa in pairs or fb in used_b:
            return False
        pairs[fa] = (fb, method)
        used_b.add(fb)
        return True

    na, nb = named_handlers(a.t), named_handlers(b.t)
    for k in na.keys() & nb.keys():
        add(na[k], nb[k], "name")

    big_a = [f for f in a.idx.funcs if a.size[f] >= MIN_WORDS]
    big_b = [f for f in b.idx.funcs if b.size[f] >= MIN_WORDS]
    fa_u, fb_u = unique_by(a.fingerprint, big_a), unique_by(b.fingerprint, big_b)
    for k in fa_u.keys() & fb_u.keys():
        add(fa_u[k], fb_u[k], "exact")

    skey = lambda s: (lambda f: frozenset(s.strings[f]) if s.strings.get(f) else None)
    sa_u, sb_u = unique_by(skey(a), big_a), unique_by(skey(b), big_b)
    for k in sa_u.keys() & sb_u.keys():
        fa, fb = sa_u[k], sb_u[k]
        if 0.5 <= a.size[fa] / b.size[fb] <= 2:
            add(fa, fb, "strings")

    changed = True
    while changed:
        changed = False
        for fa, (fb, _) in list(pairs.items()):
            ca, cb = a.callees.get(fa, []), b.callees.get(fb, [])
            if len(ca) != len(cb):
                continue
            for xa, xb in zip(ca, cb):
                if xa in pairs or xb in used_b or xa not in a.size or xb not in b.size:
                    continue
                sa, sb = a.size[xa], b.size[xb]
                same = sa >= 2 and a.fingerprint(xa) == b.fingerprint(xb)
                if same or (sa >= MIN_WORDS and 0.8 <= sa / max(sb, 1) <= 1.25):
                    changed |= add(xa, xb, "callee_exact" if same else "callee")
    return pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", default="mp")
    ap.add_argument("--to", dest="dst", default="sp_zm")
    ap.add_argument("--transfer", action="store_true",
                    help="copy curated functions/globals of --from into data/<to>/ (existing entries win)")
    args = ap.parse_args()
    a, b = Side(args.src), Side(args.dst)
    pairs = match(a, b)
    from names import load_names
    names = load_names(args.src)
    out = targets.ROOT / "data" / "cross" / f"{args.src}_{args.dst}.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([f"{args.src}_addr", f"{args.dst}_addr", "method", f"{args.src}_name"])
        for fa in sorted(pairs):
            fb, m = pairs[fa]
            w.writerow([f"0x{fa:08X}", f"0x{fb:08X}", m, names.get(fa, "")])
    print(f"{len(pairs)} matches of {len(a.idx.funcs)} {args.src} functions:",
          dict(Counter(m for _, m in pairs.values())))
    if args.transfer:
        transfer(a, b, pairs)


RANK = {"guess": 0, "likely": 1, "confirmed": 2}


def transferred_confidence(a, b, fa, fb, method, conf):
    """Structural matches cap the confidence; only matches backed by a shared string keep 'confirmed'."""
    shared = bool(a.strings.get(fa, set()) & b.strings.get(fb, set()))
    cap = {"name": "confirmed", "exact": "confirmed", "strings": "confirmed",
           "callee_exact": "likely", "callee": "guess"}[method]
    if cap == "confirmed" and not shared and method != "name":
        cap = "likely"
    return min(conf, cap, key=RANK.get)


def map_globals(a, b, pairs):
    """MP global -> target address, voted over references at identical offsets in exact matches."""
    votes = defaultdict(Counter)
    for fa, (fb, method) in pairs.items():
        if method not in ("exact", "callee_exact", "name"):
            continue
        for i in range(a.size[fa]):
            ra = a.ref_pcs.get(fa + i * 4)
            rb = b.ref_pcs.get(fb + i * 4)
            if ra is not None and rb is not None:
                votes[ra][rb] += 1
    return votes


def transfer(a, b, pairs):
    from db import Db
    src, dst = Db(a.name), Db(b.name)
    nf = 0
    for addr, r in src.funcs.items():
        if addr not in pairs or pairs[addr][0] in dst.funcs:
            continue
        fb, method = pairs[addr]
        conf = transferred_confidence(a, b, addr, fb, method, r["confidence"])
        notes = f"matched from {a.name} 0x{addr:08X} ({method}). {r['notes']}".strip()
        dst.func(fb, r["name"], r["prototype"], r["subsystem"], conf, notes)
        nf += 1
    votes = map_globals(a, b, pairs)
    ng = 0
    known = {g["name"] for g in dst.globs.values()}
    for addr, r in src.globs.items():
        if r["name"] in known or not votes.get(addr):
            continue
        (gb, n), = votes[addr].most_common(1)
        total = sum(votes[addr].values())
        conf = min(r["confidence"], "likely" if n >= 3 and n == total else "guess", key=RANK.get)
        dst.glob(gb, r["name"], r["type"], r["size"], r["subsystem"], conf,
                 f"matched from {a.name} 0x{addr:08X} ({n}/{total} code refs agree). {r['notes']}".strip())
        ng += 1
    dst.save()
    print(f"transferred {nf} functions, {ng} globals into data/{b.name}/")


if __name__ == "__main__":
    main()
