"""Single-instruction constant propagation step for PPU code.

`step()` updates gpr/fpr dicts of known constant values and reports the absolute
address an instruction references (if any). It models the instructions used to
materialise addresses and call arguments; every other register write clears the
destination, so stale values never leak into later references.
"""
import struct

M64 = (1 << 64) - 1
# X-form (opcode 31) logical/shift ops whose destination is rA instead of rD.
XO31_DEST_RA = {24, 26, 27, 28, 58, 60, 124, 284, 316, 412, 413, 444, 476, 536, 539, 792, 794, 824, 922, 954, 986}
# opcode 31 stores (no register write except update forms, which write rA).
XO31_STORES = {150, 151, 149, 181, 182, 183, 214, 215, 247, 407, 439, 662, 663, 695, 727, 759, 918, 983, 231, 487,
               135, 167, 199, 231, 919, 54, 86, 246, 278, 470, 1014, 982}
XO31_UPDATE_STORES = {183, 247, 439, 695, 759, 181, 55, 119, 311, 375, 567, 631, 53}
XO31_FP_LOADS = {535, 567, 599, 631, 855}
VOLATILE_GPR = range(0, 13)
VOLATILE_FPR = range(0, 14)


def sext16(v):
    return v - 0x10000 if v & 0x8000 else v


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def step(g, f, pc, w, toc, read_float=None):
    """Advance one instruction. Returns the referenced absolute address or None."""
    op = w >> 26
    rd, ra, rb = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    imm = w & 0xFFFF
    ref = None
    if op == 18 or op == 16:
        if w & 1:  # bl / bcl: callee clobbers volatile registers
            for r in VOLATILE_GPR:
                g.pop(r, None)
            for r in VOLATILE_FPR:
                f.pop(r, None)
        return None
    if op == 19:
        if w & 1:
            for r in VOLATILE_GPR:
                g.pop(r, None)
            for r in VOLATILE_FPR:
                f.pop(r, None)
        return None
    if op == 14:  # addi / li
        if ra == 0:
            g[rd] = sext16(imm) & M64
        elif ra in g:
            ref = g[rd] = (g[ra] + sext16(imm)) & M64
        else:
            g.pop(rd, None)
    elif op == 15:  # addis / lis
        if ra == 0:
            g[rd] = (sext16(imm) << 16) & M64
        elif ra in g:
            g[rd] = (g[ra] + (sext16(imm) << 16)) & M64
        else:
            g.pop(rd, None)
    elif op in (24, 25):  # ori / oris: dest ra, source rd
        if rd in g:
            g[ra] = g[rd] | (imm << (16 if op == 25 else 0))
            if op == 24 and imm:
                ref = g[ra]
        else:
            g.pop(ra, None)
    elif op in (26, 27, 28, 29, 20, 21, 23):
        g.pop(ra, None)
    elif op == 30:
        if (w >> 2) & 7 == 0 and rd in g:  # rldicl (clrldi/srdi/rotldi)
            sh = ((w >> 11) & 31) | ((w >> 1) & 1) << 5
            mb = ((w >> 6) & 31) | ((w >> 5) & 1) << 5
            v = g[rd]
            rot = ((v << sh) | (v >> (64 - sh))) & M64 if sh else v
            g[ra] = rot & ((1 << (64 - mb)) - 1)
        else:
            g.pop(ra, None)
    elif op == 31:
        xo = (w >> 1) & 0x3FF
        if xo == 444 and rd == rb:  # mr
            if rd in g:
                g[ra] = g[rd]
            else:
                g.pop(ra, None)
        elif xo in XO31_DEST_RA:
            g.pop(ra, None)
        elif xo in XO31_STORES:
            if xo in XO31_UPDATE_STORES:
                g.pop(ra, None)
        elif xo in XO31_FP_LOADS:
            f.pop(rd, None)
        elif xo in (0, 32, 144, 146, 210, 242, 598, 854, 470, 86, 54, 278, 246, 1014, 982, 339 + 1000):
            pass  # cmp/cmpl/mtcrf/mtmsr/sync/eieio/dcb*/icbi
        elif xo == 467:  # mtspr
            pass
        else:
            g.pop(rd, None)
    elif 32 <= op <= 47:  # integer loads/stores (D-form)
        if ra == 2:
            ref = (toc + sext16(imm)) & 0xFFFFFFFF
        elif ra and ra in g:
            ref = (g[ra] + sext16(imm)) & 0xFFFFFFFF
        is_load = op in (32, 33, 34, 35, 40, 41, 42, 43, 46)
        if is_load:
            g.pop(rd, None)
        if op in (33, 35, 37, 39, 41, 43, 45):  # update forms write ra
            g.pop(ra, None)
    elif 48 <= op <= 55:  # FP loads/stores
        ea = None
        if ra == 2:
            ea = (toc + sext16(imm)) & 0xFFFFFFFF
        elif ra and ra in g:
            ea = (g[ra] + sext16(imm)) & 0xFFFFFFFF
        ref = ea
        if op <= 51:
            val = read_float(ea, op >= 50) if (ea is not None and read_float) else None
            if val is None:
                f.pop(rd, None)
            else:
                f[rd] = val
        if op in (49, 51, 53, 55):
            g.pop(ra, None)
    elif op in (58, 62):  # ld/ldu/lwa, std/stdu
        d = sext16(imm & ~3)
        if ra == 2:
            ref = (toc + d) & 0xFFFFFFFF
        elif ra and ra in g:
            ref = (g[ra] + d) & 0xFFFFFFFF
        if op == 58:
            g.pop(rd, None)
        if imm & 3 == 1:
            g.pop(ra, None)
    elif op in (59, 63):
        xo10 = (w >> 1) & 0x3FF
        if op == 63 and xo10 == 72:  # fmr
            if rb in f:
                f[rd] = f[rb]
            else:
                f.pop(rd, None)
        elif op == 63 and xo10 == 40:  # fneg
            if rb in f:
                f[rd] = -f[rb]
            else:
                f.pop(rd, None)
        elif op == 63 and xo10 in (0, 32):  # fcmpu/fcmpo
            pass
        else:
            f.pop(rd, None)
    elif op in (7, 8, 12, 13):  # mulli, subfic, addic, addic.
        g.pop(rd, None)
    elif op == 4:  # VMX: only touches vector registers
        pass
    return ref


def float_reader(elf):
    def read(addr, double):
        try:
            return struct.unpack(">d" if double else ">f", elf.read(addr, 8 if double else 4))[0]
        except ValueError:
            return None
    return read
