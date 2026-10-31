# 01 — Memory map (MP, TU13)

PS3 userland is a 32-bit address space even though the PPU runs in 64-bit mode.

## Sections

Names are reconstructed (the original `.shstrtab` is zeroed). `?` = inferred from content only.

| # | Name | Address | Size | Notes |
|---|---|---|---|---|
| 1 | `.init` | `0x00010200` | `0x2C` | |
| 2 | `.text` | `0x00010230` | `0x8B35BC` | all game code |
| 3 | `.fini` | `0x008C37EC` | `0x24` | |
| 4 | `.sceStub.text` | `0x008C3810` | `0x45C8` | 319 import trampolines, 0x38 bytes each |
| 5 | `.rodata.sceResident` | `0x008C7DD8` | `0x18C` | import library name strings |
| 6 | `.rodata.sceFNID` | `0x008C7F64` | `0x4FC` | 319 import NIDs |
| 7–11 | `.lib.ent.top` … `.lib.stub.btm` | `0x008C8460` | | `.lib.stub` = 25 × 0x2C library descriptors |
| 12 | `.rodata` | `0x008C88C0` | `0xAB7E0` | strings, float constants, tables |
| 13 | `.rodata.guid?` | `0x009740A0` | `0x20` | starts with `\x7fGUID`, referenced from PRX_PARAM |
| 14 | `.spu_image?` | `0x00974100` | `0x1B6B00` | writable, looks like embedded SPU code/ELFs |
| 15 | `.sys_proc_param` | `0x00B2AC00` | `0x28` | |
| 16 | `.sys_proc_prx_param` | `0x00B2AC28` | `0x40` | |
| 17 | `.ctors` | `0x00B30000` | `0x2B4` | `0xFFFFFFFF` + OPD pointers |
| 18 | `.dtors` | `0x00B302B4` | `0xC0` | |
| 20 | `.data.rel.ro?` | `0x00B30380` | `0x15950` | pointer tables, incl. builtin tables (`0xB311D8`…) |
| 21 | `.data.sceFStub` | `0x00B45CD0` | `0x4FC` | import slots, patched by the loader |
| 22 | `.opd` | `0x00B461D0` | `0x9518` | **4771 function descriptors** `{func, toc}` |
| 23 | `.toc` | `0x00B4F6E8` | `0x10EC` | TOC base r2 = `0x00B576E8` (= start + 0x8000) |
| 24/25 | `.tdata`/`.tbss` | `0x00B507D4` | `0xD`/`0x2BC` | TLS image |
| 26 | `.data` | `0x00B50B00` | `0x16BBC` | |
| 27 | `.bss` | `0x00B67700` | `0x1C42098` | **~28 MB**, nearly all mutable game state |

## Important globals

All in `.bss` unless noted. Full list: [`data/mp/globals.csv`](../../data/mp/globals.csv).

| Address | Name | Notes |
|---|---|---|
| `0x012AB290` | `g_entities` | `gentity_t[]`, stride `0x2F8` |
| `0x01213800` | `level` | `level_locals_t`; `level.clients` at `+0x0` |
| `0x013950C8` | `g_clients` | `gclient_t[]`, stride `0x2A38` |
| `0x018F01B0` | `s_dvarPool` | `dvar_t[4096]`, stride `0x70` |
| `0x019601B4` | `s_dvarHashTable` | 1024 buckets |
| `0x019611BC` | `s_sortedDvars` | |
| `0x014648AC` | `cmd_functions` | client command list |
| `0x014648B0` | `sv_cmd_functions` | server command list |

Script VM per-instance state lives around `0x01E8B200` (scrVarPub, stride `0x58` per instance)
and `0x01E93EF4…` (scrVmPub, stride `0x4320`) — see [04-gsc-vm.md](04-gsc-vm.md).

## Imports

`data/mp/imports.csv`: for each import, `stub_slot` is the `.data.sceFStub` word the loader
patches, `stub_code` the trampoline in `.sceStub.text` that game code `bl`s to. Libraries:
cellAudio, cellGame, cellGcmSys, cellHttp, cellL10n, cellMic, cellNetCtl, cellRec, cellResc,
cellRtc, cellSpurs, cellSsl, cellSync, cellSysmodule, cellSysutil, cellSysutilAvconfExt,
cellUserInfo, cellVoice, sceNp, sceNpCommerce2, sceNpTrophy, sysPrxForUser, sys_fs, sys_io, sys_net.
