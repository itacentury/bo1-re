"""Per-binary configuration: data/<target>/target.json plus layout derived from the ELF.

The active target comes from the BO1_TARGET environment variable (default "mp"), so the
script-style tools (disasm.py, overview.py, ...) need no extra arguments.
"""
import json
import os
import struct
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ("mp", "sp_zm")
SHF_WRITE, SHF_EXECINSTR = 1, 4


def current() -> str:
    t = os.environ.get("BO1_TARGET", "mp")
    if t not in TARGETS:
        raise SystemExit(f"BO1_TARGET must be one of {TARGETS}, not {t!r}")
    return t


def hexint(v):
    return int(v, 16) if isinstance(v, str) else v


class Target:
    def __init__(self, name: str):
        self.name = name
        self.data_dir = ROOT / "data" / name
        self.config = json.loads((self.data_dir / "target.json").read_text())
        self.binary = ROOT / self.config["binary"]
        self.elf_path = ROOT / f"build/EBOOT_{name.upper()}.elf"
        self.include_dir = ROOT / "include" / f"bo1_{name}"
        self.sections = self.config["sections"]

    @property
    def anchors(self) -> dict:
        return self.config.get("anchors", {})

    def anchor(self, key: str):
        v = self.anchors.get(key)
        return hexint(v) if v else None

    @property
    def builtin_tables(self):
        """(start, stride, table name, lookup function or None)."""
        return [(hexint(s), st, n, hexint(l) if l else None) for s, st, n, l in self.config.get("builtin_tables", [])]

    @property
    def builtin_prefix_ranges(self):
        """(first entry, last entry, handler name prefix) for sub-blocks of a combined table."""
        return [(hexint(a), hexint(b), prefix) for a, b, prefix in self.config.get("builtin_prefix_ranges", [])]

    @property
    def stats(self) -> dict:
        """Stats DDL buffer layout ({} when the target has none)."""
        return self.config.get("stats", {})

    @property
    def dvar_register_funcs(self) -> dict:
        """dvar type -> Dvar_Register<Type> address."""
        return {t: hexint(a) for t, a in self.config.get("dvar_register_funcs", {}).items()}

    # Layout derived from the ELF section headers (names are zeroed, flags/addresses are not).
    @lru_cache(maxsize=None)
    def _shdrs(self):
        d = self.elf_path.read_bytes()
        shoff, = struct.unpack(">Q", d[0x28:0x30])
        shnum, = struct.unpack(">H", d[0x3C:0x3E])
        out = []
        for i in range(shnum):
            _, _, flags, addr, _, size = struct.unpack(">IIQQQQ", d[shoff + i * 64:shoff + i * 64 + 40])
            out.append((flags, addr, size))
        entry, = struct.unpack(">Q", d[0x18:0x20])
        return out, entry

    def section(self, name: str):
        """(start, end) of a named section; names come from target.json."""
        i = self.sections.index(name)
        _, addr, size = self._shdrs()[0][i]
        return addr, addr + size

    @property
    def text(self):
        return self.section(".text")

    @property
    def stub(self):
        return self.section(".sceStub.text")

    @property
    def opd(self):
        return self.section(".opd")


@lru_cache(maxsize=None)
def get(name: str = None) -> Target:
    return Target(name or current())
