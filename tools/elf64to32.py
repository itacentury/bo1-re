#!/usr/bin/env python3
"""Rewrite a PS3 ELF64 (EM_PPC64) as ELF32 (EM_PPC) so 32-bit-only ELF tooling accepts it.

Segment contents stay byte-identical; only the ELF/program/section headers are re-encoded.
PS3 userland addresses fit in 32 bits, so nothing is truncated. The instruction set is still
64-bit PPU code: load the result with a 64-bit-ISA/32-bit-address language
(Ghidra: PowerPC:BE:64:64-32addr).
"""
import argparse
import csv
import struct
import sys
from pathlib import Path

EM_PPC = 20
PT_NAMES_KEEP = (1, 7)  # PT_LOAD, PT_TLS; Sony PT_PROC_PARAM/PRX_PARAM confuse generic loaders


def convert(d: bytes) -> bytes:
    if d[:4] != b"\x7fELF" or d[4] != 2 or d[5] != 2:
        sys.exit("expected a big-endian ELF64")
    e_type, _, e_version, entry, phoff, shoff, flags, _, _, phnum, _, shnum, shstrndx = struct.unpack(
        ">HHIQQQIHHHHHH", d[16:64])

    phdrs = []
    for i in range(phnum):
        p_type, p_flags, off, va, pa, fs, ms, al = struct.unpack(">IIQQQQQQ", d[phoff + i * 56:phoff + i * 56 + 56])
        if p_type in PT_NAMES_KEEP:
            phdrs.append(struct.pack(">8I", p_type, off, va, pa, fs, ms, p_flags & 7, al))
    shdrs = []
    for i in range(shnum):
        nm, ty, fl, ad, off, sz, ln, inf, al, es = struct.unpack(">IIQQQQIIQQ", d[shoff + i * 64:shoff + i * 64 + 64])
        shdrs.append(struct.pack(">10I", nm, ty, fl, ad, off, sz, ln, inf, al, es))

    out = bytearray(d)
    # The ELF32 header + program headers replace the old ones inside the first (non-code) 0x200 bytes.
    new_phoff = 52
    if new_phoff + 32 * len(phdrs) > 0x200:
        sys.exit("program headers do not fit before .init")
    new_shoff = (len(out) + 3) & ~3
    out += b"\0" * (new_shoff - len(out)) + b"".join(shdrs)
    ident = d[:16]
    ident = ident[:4] + b"\x01" + ident[5:]  # ELFCLASS32
    hdr = ident + struct.pack(">HHIIIIIHHHHHH", e_type, EM_PPC, e_version, entry, new_phoff, new_shoff,
                              flags & 0x7FFFFFFF, 52, 32, len(phdrs), 40, shnum, shstrndx)
    out[0:0x200] = (hdr + b"".join(phdrs)).ljust(0x200, b"\0")
    return bytes(out)


def collect_symbols(data_dir: Path, func_starts):
    """Database names + every known entry point as (name, value, size, kind)."""
    from names import auto_function_names
    named = {a: (n, "func") for a, n in auto_function_names(data_dir.name).items()}
    rows = lambda f: csv.DictReader((data_dir / f).open()) if (data_dir / f).exists() else []
    for r in rows("imports.csv"):
        named[int(r["stub_code"], 16)] = (r["name"], "func")
    for r in rows("functions.csv"):
        named[int(r["addr"], 16)] = (r["name"], "func")
        if r["opd"]:
            named[int(r["opd"], 16)] = (f"__opd_{r['name']}", "object")
    for r in rows("globals.csv"):
        named[int(r["addr"], 16)] = (r["name"], "object")
    seen = {}
    for r in rows("dvars.csv"):
        if r["dvar_ptr"]:
            base = f"dvar_{r['name']}"
            seen[base] = seen.get(base, 0) + 1
            nm = base if seen[base] == 1 else f"{base}_{seen[base]}"
            named.setdefault(int(r["dvar_ptr"], 16), (nm, "object"))
    starts = sorted(set(func_starts) | {a for a, (_, k) in named.items() if k == "func"})
    size = {a: (b - a) for a, b in zip(starts, starts[1:])}
    used = set()
    for a in starts:
        name = named.get(a, (f"sub_{a:X}", "func"))[0]
        if name in used:
            name = f"{name}_{a:X}"
        used.add(name)
        yield name, a, size.get(a, 4), "func"
    for a, (name, kind) in sorted(named.items()):
        if kind == "object":
            yield (name if name not in used else f"{name}_{a:X}"), a, 4, "object"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("elf64")
    ap.add_argument("elf32")
    ap.add_argument("--symbols", metavar="DATA_DIR", help="append .symtab built from data/<target>/ + scanner")
    args = ap.parse_args()
    with open(args.elf64, "rb") as f:
        out = convert(f.read())
    if args.symbols:
        import ppcscan
        import target as targets
        from symelf import add_symbols
        t = targets.get(Path(args.symbols).name)
        syms = list(collect_symbols(t.data_dir, ppcscan.load(t.name).funcs))
        out = add_symbols(out, syms, t.sections)
        print(f"added {len(syms)} symbols")
    with open(args.elf32, "wb") as f:
        f.write(out)
    print(f"wrote {args.elf32}")


if __name__ == "__main__":
    main()
