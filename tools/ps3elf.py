"""Minimal big-endian PS3 ELF reader shared by the tools in this directory."""
import struct
from dataclasses import dataclass


@dataclass
class Segment:
    vaddr: int
    offset: int
    filesz: int
    memsz: int
    flags: int


class Ps3Elf:
    def __init__(self, path: str):
        with open(path, "rb") as f:
            self.data = f.read()
        d = self.data
        self.entry = struct.unpack(">Q", d[0x18:0x20])[0]
        phoff = struct.unpack(">Q", d[0x20:0x28])[0]
        phnum = struct.unpack(">H", d[0x38:0x3A])[0]
        self.segments = []
        for i in range(phnum):
            p_type, p_flags, p_offset, p_vaddr, _, p_filesz, p_memsz = struct.unpack(
                ">IIQQQQQ", d[phoff + i * 56:phoff + i * 56 + 48])
            if p_type == 1 and p_memsz:
                self.segments.append(Segment(p_vaddr, p_offset, p_filesz, p_memsz, p_flags))
        # The entry point is an OPD descriptor {func, toc}; its toc word is the global r2 value.
        self.toc = self.u32(self.entry + 4)

    def offset(self, va: int) -> int:
        for s in self.segments:
            if s.vaddr <= va < s.vaddr + s.filesz:
                return s.offset + va - s.vaddr
        raise ValueError(f"address {va:#x} not backed by file data")

    def segment_of(self, va: int):
        return next((s for s in self.segments if s.vaddr <= va < s.vaddr + s.memsz), None)

    def read(self, va: int, size: int) -> bytes:
        o = self.offset(va)
        return self.data[o:o + size]

    def u32(self, va: int) -> int:
        return struct.unpack(">I", self.read(va, 4))[0]

    def cstr(self, va: int) -> str:
        o = self.offset(va)
        return self.data[o:self.data.index(b"\0", o)].decode("latin-1")

    def prx_param(self) -> dict:
        # sys_process_prx_param_t lives at the PT 0x60000002 segment.
        phoff = struct.unpack(">Q", self.data[0x20:0x28])[0]
        phnum = struct.unpack(">H", self.data[0x38:0x3A])[0]
        for i in range(phnum):
            p_type, _, _, p_vaddr = struct.unpack(">IIQQ", self.data[phoff + i * 56:phoff + i * 56 + 24])
            if p_type == 0x60000002:
                f = struct.unpack(">8I", self.read(p_vaddr, 32))
                return {"libent_start": f[4], "libent_end": f[5], "libstub_start": f[6], "libstub_end": f[7]}
        raise ValueError("no PRX_PARAM segment")

    def imports(self):
        """Yield (library, index, nid, stub_slot_addr) for every imported function."""
        pp = self.prx_param()
        va = pp["libstub_start"]
        while va < pp["libstub_end"]:
            hdr = self.read(va, 0x2C)
            size, _, _, _, nfunc = struct.unpack(">BBHHH", hdr[:8])
            name_ptr, nid_tab, stub_tab = struct.unpack(">III", hdr[0x10:0x1C])
            lib = self.cstr(name_ptr)
            for i in range(nfunc):
                yield lib, i, self.u32(nid_tab + i * 4), stub_tab + i * 4
            va += size

    def opd_entries(self, start: int, end: int):
        """Yield (opd_addr, func_addr, toc) for 8-byte PS3 function descriptors."""
        for va in range(start, end, 8):
            yield va, self.u32(va), self.u32(va + 4)
