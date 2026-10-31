# 02 — Cell PPU ABI quirks that matter for RE and mods

## 64-bit CPU, 32-bit pointers

The PPU executes 64-bit PowerPC code (`ld`/`std`, `rldicl`, `mulld` …), but every pointer
is 32 bits. The compiler zero-extends addresses all the time — `clrldi rX, rY, 32` appears
after almost every pointer computation. Ghidra must use **`PowerPC:BE:64:64-32addr`**;
a 32-bit PPC language mis-decodes the 64-bit instructions, a plain 64-bit one invents
64-bit pointers.

## Function descriptors (OPD)

A function pointer points to an 8-byte descriptor in `.opd`, not to code:

```c
typedef struct { uint32_t func; uint32_t toc; } opd_t;   /* PS3 uses 2 words, not 3 */
```

Values below are MP; SP/ZM follows the same rules with its own addresses (entry `0xA43AA0`,
OPDs `0xA43A90`–`0xA4C4B0`, r2 = `0x00A544B0`, 4420 OPDs).

- The entry point (`e_entry = 0xB461E0`) is an OPD.
- Every callback table (`Cmd_AddCommand` handlers, GSC builtin tables, `.ctors`) stores **OPD
  addresses** (`0xB46xxx`–`0xB4Fxxx`). `data/<target>/*.csv` lists both `handler` (code) and
  `handler_opd`.
- Direct calls (`bl`) go to code and never touch the OPD.
- Only 4771 of ~15600 functions have an OPD — the others are never address-taken. To call
  one from a mod, build your own descriptor `{addr, 0x00B576E8}` (`include/bo1_<target>/functions.h`
  does this for you).

## TOC / r2

All game code shares **one TOC: r2 = `0x00B576E8`**. The game mostly loads string and global
addresses with absolute `lis`/`addi` pairs; `.toc` is small (`0x10EC` bytes). A mod with its
own TOC must restore r2 before calling into the game — an OPD with the game TOC does that.

## Argument passing (64-bit ELF ABI)

- Integer/pointer args in `r3..r10`, floats in `f1..f13`, return in `r3` / `f1`.
- **Every float argument also consumes a GPR slot.**
  `Dvar_RegisterFloat(name, value, min, max, flags, desc)` → `name=r3`, `value/min/max=f1..f3`,
  `r4..r6` skipped, `flags=r7`, `desc=r8`. C callers get this right automatically; hand-written
  hooks and argument recovery must account for it.
- Structs ≤ 16 bytes passed by value travel in GPR pairs (`DvarValue`, `DvarLimits` in
  `Dvar_RegisterNew`).
- Arguments that do not fit in `r3..r10` go to the caller's parameter save area at
  `0x70(r1)` and up (e.g. `color`/`style` of `R_AddCmdDrawText`).
- Non-volatile: `r14..r31`, `f14..f31`. Registration functions preload float constants into
  `f2x` registers once at function entry — argument recovery has to simulate from the start
  of the function, not just a few instructions before the call.

## Atomic sequences

Locks use `lwarx`/`stwcx.` loops (e.g. dvar reader/writer counters at `0x18F01A4/8`). Ghidra
renders them as `storeWordConditionalIndexed` with an `in_RESERVE` pseudo-variable.

## Script entity references

GSC method handlers receive `scr_entref_t` as a 32-bit value in `r3`: two `u16` halves
(`entnum`, `classnum`); handlers reject `classnum != 0` with "not an entity".
