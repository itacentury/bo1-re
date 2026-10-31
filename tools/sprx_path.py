#!/usr/bin/env python3
"""Show or change the SPRX path loaded at startup by a patched (SPRX-loader) EBOOT."""
import argparse
import hashlib
import re
import struct
import sys

from self2elf import extract

# lis r3,HI / ori r3,r3,LO / li r4,0 / li r5,0 / li r11,0x1E0 (sys_prx_load_module) / sc
LOADER = re.compile(rb"\x3c\x60(..)\x60\x63(..)\x38\x80\x00\x00\x38\xa0\x00\x00\x39\x60\x01\xe0\x44\x00\x00\x02",
                    re.DOTALL)
# The path overwrites the "GCC: (GNU) 4.1.1 (SDK330, $Rev: 3378 $)" .comment string of an embedded
# SPU ELF: 39 characters + NUL.
SLOT_SIZE = 40


def path_offset(data: bytes, elf: bytes, header_len: int) -> int:
    hits = list(LOADER.finditer(elf))
    if len(hits) != 1:
        sys.exit(f"no SPRX loader found ({len(hits)} matches)")
    hi, lo = struct.unpack(">HH", hits[0].group(1) + hits[0].group(2))
    va = hi << 16 | lo
    phoff = struct.unpack(">Q", elf[0x20:0x28])[0]
    phnum = struct.unpack(">H", elf[0x38:0x3A])[0]
    for i in range(phnum):
        p_type, _, p_offset, p_vaddr, _, p_filesz = struct.unpack(">IIQQQQ", elf[phoff + i * 56:phoff + i * 56 + 40])
        if p_type == 1 and p_vaddr <= va and va + SLOT_SIZE <= p_vaddr + p_filesz:
            return header_len + p_offset + va - p_vaddr
    sys.exit(f"path address {va:#x} not inside a PT_LOAD")


def digest_offset(data: bytes) -> int:
    # Control info list; the type 2 entry (size 0x40) holds digest2 = SHA-1 of the ELF at +0x24.
    ci_off, ci_size = struct.unpack(">QQ", data[0x58:0x68])
    off = ci_off
    while off < ci_off + ci_size:
        typ, size, more = struct.unpack(">IIQ", data[off:off + 0x10])
        if typ == 2 and size == 0x40:
            return off + 0x24
        if not more:
            break
        off += size
    sys.exit("no digest entry in control info")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("eboot")
    ap.add_argument("new_path", nargs="?", help=f"e.g. /dev_hdd0/tmp/MyMenu.sprx (max {SLOT_SIZE - 1} chars)")
    ap.add_argument("-o", "--output", help="output file (default: overwrite the input)")
    args = ap.parse_args()

    with open(args.eboot, "rb") as f:
        data = bytearray(f.read())
    header_len, data_len = struct.unpack(">QQ", data[0x10:0x20])
    elf = extract(bytes(data))
    off = path_offset(data, elf, header_len)
    old = bytes(data[off:data.index(b"\0", off)]).decode("latin-1")

    if args.new_path is None:
        print(f"{old}  (max {SLOT_SIZE - 1} chars)")
        return

    new = args.new_path
    if not new.isascii() or not new.startswith("/"):
        sys.exit("path must be ASCII and absolute, e.g. /dev_hdd0/tmp/MyMenu.sprx")
    if len(new) + 1 > SLOT_SIZE:
        sys.exit(f"path is {len(new)} chars, max is {SLOT_SIZE - 1}")

    data[off:off + SLOT_SIZE] = new.encode().ljust(SLOT_SIZE, b"\0")
    d = digest_offset(data)
    data[d:d + 20] = hashlib.sha1(data[header_len:header_len + data_len]).digest()

    out = args.output or args.eboot
    with open(out, "wb") as f:
        f.write(data)
    print(f"{old} -> {new}  ({out})")


if __name__ == "__main__":
    main()
