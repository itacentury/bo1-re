#!/usr/bin/env python3
"""Build a PS3HEN EBOOT (NPDRM SELF) from a patched (SPRX-loader) CFW EBOOT with a new SPRX path.

HEN does not run fake-signed SELFs, so the ELF is re-signed with scetool (keys required, not in this repo).
The reference HEN EBOOT differs from the CFW one only in the container and in sys_process_param.sdk_version.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile

from self2elf import ELF_MAGIC, extract
from sprx_path import SLOT_SIZE, path_offset

PT_PROC_PARAM = 0x60000001
SDK_CFW = 0x00340001
SDK_HEN = 0x00330001
CONTENT_ID = "JP9000-NPJA00001_00-0000000000000000"

SCETOOL_ARGS = [
    "--sce-type=SELF",
    "--compress-data=TRUE",
    "--skip-sections=FALSE",
    "--self-add-shdrs=TRUE",
    "--key-revision=04",
    "--self-auth-id=1010000001000003",
    "--self-vendor-id=01000002",
    "--self-type=NPDRM",
    "--self-app-version=0001000000000000",
    "--np-license-type=FREE",
    "--np-app-type=EXEC",
    f"--np-content-id={CONTENT_ID}",
    "--np-real-fname=EBOOT.BIN",
]


def load_elf(path: str) -> bytearray:
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] == ELF_MAGIC:
        return bytearray(data)
    return bytearray(extract(data))


def sdk_version_offset(elf: bytes) -> int:
    phoff = struct.unpack(">Q", elf[0x20:0x28])[0]
    phnum = struct.unpack(">H", elf[0x38:0x3A])[0]
    for i in range(phnum):
        p_type, _, p_offset = struct.unpack(">IIQ", elf[phoff + i * 56:phoff + i * 56 + 16])
        if p_type == PT_PROC_PARAM:
            # sys_process_param_t: size, magic, version, sdk_version
            return p_offset + 0xC
    sys.exit("no PT_PROC_PARAM segment")


def print_header(path: str) -> None:
    with open(path, "rb") as f:
        d = f.read()
    key_rev = struct.unpack(">H", d[0x08:0x0A])[0]
    ai = struct.unpack(">Q", d[0x28:0x30])[0]
    auth, vendor, self_type = struct.unpack(">QII", d[ai:ai + 16])
    ci_off, ci_size = struct.unpack(">QQ", d[0x58:0x68])
    content_id = "-"
    off = ci_off
    while off < ci_off + ci_size:
        typ, size, more = struct.unpack(">IIQ", d[off:off + 0x10])
        if typ == 3:
            content_id = d[off + 0x20:off + 0x50].split(b"\0")[0].decode("latin-1")
        if not more or not size:
            break
        off += size
    print(f"key rev {key_rev:#x}, self type {self_type}, auth {auth:016X}, vendor {vendor:08X}, "
          f"content ID {content_id}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("eboot", help="CFW EBOOT (fake-signed SELF) or plain ELF, e.g. from rpcs3 --decrypt")
    ap.add_argument("new_path", help=f"e.g. /dev_hdd0/tmp/MyMenu.sprx (max {SLOT_SIZE - 1} chars)")
    ap.add_argument("-o", "--output", required=True, help="HEN EBOOT to write")
    ap.add_argument("--scetool", default=os.environ.get("SCETOOL", "scetool"),
                    help="scetool binary (default: $SCETOOL or scetool on PATH)")
    ap.add_argument("--elf", help="also keep the patched ELF at this path")
    args = ap.parse_args()

    new = args.new_path
    if not new.isascii() or not new.startswith("/"):
        sys.exit("path must be ASCII and absolute, e.g. /dev_hdd0/tmp/MyMenu.sprx")
    if len(new) + 1 > SLOT_SIZE:
        sys.exit(f"path is {len(new)} chars, max is {SLOT_SIZE - 1}")

    scetool = shutil.which(args.scetool)
    if not scetool:
        sys.exit(f"scetool not found ({args.scetool}), set --scetool or $SCETOOL")

    elf = load_elf(args.eboot)
    off = path_offset(bytes(elf), bytes(elf), 0)
    old = bytes(elf[off:elf.index(b"\0", off)]).decode("latin-1")
    elf[off:off + SLOT_SIZE] = new.encode().ljust(SLOT_SIZE, b"\0")

    sdk_off = sdk_version_offset(elf)
    sdk = struct.unpack(">I", elf[sdk_off:sdk_off + 4])[0]
    if sdk not in (SDK_CFW, SDK_HEN):
        sys.exit(f"unexpected sdk_version {sdk:#010x}, not a BO1 TU13 EBOOT?")
    elf[sdk_off:sdk_off + 4] = struct.pack(">I", SDK_HEN)

    # scetool can exit 0 without writing anything (e.g. missing keys), so only a fresh file counts.
    if os.path.exists(args.output):
        os.remove(args.output)
    with tempfile.TemporaryDirectory() as tmp:
        elf_path = os.path.join(tmp, "EBOOT.ELF")
        with open(elf_path, "wb") as f:
            f.write(elf)
        if args.elf:
            shutil.copyfile(elf_path, args.elf)
        # scetool finds its keys in ./data or in the folder named by $PS3.
        res = subprocess.run([scetool, *SCETOOL_ARGS, "--encrypt", elf_path, args.output],
                             capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(args.output):
        sys.exit(f"scetool failed:\n{res.stdout}{res.stderr}")

    print(f"{old} -> {new}  ({args.output})")
    print_header(args.output)


if __name__ == "__main__":
    main()
