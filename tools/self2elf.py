#!/usr/bin/env python3
"""Extract the plain ELF from a fake-signed (unencrypted, uncompressed) PS3 SELF."""
import argparse
import struct
import sys

SCE_MAGIC = b"SCE\0"
ELF_MAGIC = b"\x7fELF"


def extract(data: bytes) -> bytes:
    if data[:4] != SCE_MAGIC:
        sys.exit("not a SELF (missing SCE magic)")
    key_rev = struct.unpack(">H", data[0x08:0x0A])[0]
    header_len, data_len = struct.unpack(">QQ", data[0x10:0x20])
    seginfo_off = struct.unpack(">Q", data[0x48:0x50])[0]
    if key_rev != 0x8000:
        sys.exit(f"key revision {key_rev:#x}: retail-encrypted SELF, decrypt it first")

    elf = data[header_len:header_len + data_len]
    if elf[:4] != ELF_MAGIC:
        sys.exit("no ELF at end of SELF header")

    phoff = struct.unpack(">Q", elf[0x20:0x28])[0]
    phnum = struct.unpack(">H", elf[0x38:0x3A])[0]
    for i in range(phnum):
        _, _, p_offset, _, _, p_filesz = struct.unpack(">IIQQQQ", elf[phoff + i * 56:phoff + i * 56 + 40])
        s_off, s_size, comp, _, enc = struct.unpack(">QQIIQ", data[seginfo_off + i * 32:seginfo_off + i * 32 + 32])
        # enc=0 marks sub-segments (TLS, PROC_PARAM) that live inside a PT_LOAD
        if comp != 1 or enc not in (0, 2):
            sys.exit(f"segment {i} is compressed/encrypted (comp={comp}, enc={enc})")
        # Every segment must sit at header_len + p_offset, otherwise the image is not contiguous.
        if p_filesz and (s_off != header_len + p_offset or s_size != p_filesz):
            sys.exit(f"segment {i} not contiguous: self={s_off:#x} elf={p_offset:#x}")
    return elf


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("self_path")
    ap.add_argument("elf_path")
    args = ap.parse_args()
    with open(args.self_path, "rb") as f:
        elf = extract(f.read())
    with open(args.elf_path, "wb") as f:
        f.write(elf)
    print(f"wrote {len(elf):#x} bytes to {args.elf_path}")


if __name__ == "__main__":
    main()
