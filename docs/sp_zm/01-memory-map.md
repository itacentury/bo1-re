# 01 — Memory map (SP/ZM, TU13)

`EBOOT_SP_ZM.BIN` is one executable for the campaign *and* Zombies (`online_tu13_sp_`,
internal name `t5_ps3f.self`). Zombies is a game mode inside it, so every address below is
valid for both modes. Layout rules are the same as MP (see [../mp/01-memory-map.md](../mp/01-memory-map.md)).

## Sections

The index list differs from MP: an extra executable section (#17) after the PRX_PARAM block
shifts every later index by one. Names are reconstructed and kept per target in
[`data/sp_zm/target.json`](../../data/sp_zm/target.json).

| # | Name | Address | Size | Notes |
|---|---|---|---|---|
| 2 | `.text` | `0x00010230` | `0x7C8DF4` | ~1 MB less code than MP |
| 4 | `.sceStub.text` | `0x007D9048` | `0x3C98` | 277 import trampolines |
| 12 | `.rodata` | `0x007DD640` | `0xA0830` | |
| 14 | `.spu_image?` | `0x0087DF00` | `0x1A4380` | |
| 16 | `.sys_proc_prx_param` | `0x00A222A8` | `0x40` | |
| 17 | `.text.prx_loader?` | `0x00A222E8` | `0x1CC` | **SP/ZM only**: raw `sc` calls 0x1E0/0x1E1 (`sys_prx_load_module` / `sys_prx_start_module`) |
| 21 | `.data.rel.ro?` | `0x00A30330` | `0x13308` | builtin tables |
| 23 | `.opd` | `0x00A43A90` | `0x8A20` | 4420 descriptors |
| 24 | `.toc` | `0x00A4C4B0` | `0x10F4` | r2 = **`0x00A544B0`** |
| 27 | `.data` | `0x00A4D880` | `0x1663C` | |
| 28 | `.bss` | `0x00A63F00` | `0x173E298` | ~23 MB |

## Important globals

Full list: [`data/sp_zm/globals.csv`](../../data/sp_zm/globals.csv).

| Address | Name | Notes |
|---|---|---|
| `0x00FA805C` | `g_entities` | `gentity_t[]`, stride **`0x34C`** (MP `0x2F8`) |
| `0x00FA2800` | `level` | `level.clients` at `+0x0`, `gclient_t` stride **`0x1D30`** (MP `0x2A38`) |
| `0x013DF860` | `s_dvarPool` | `dvar_t[4096]`, stride `0x70` |
| `0x0144F864` | `s_dvarHashTable` | pool + `0x70004`, same as MP |
| `0x011FC92C` | `cmd_functions` | client command list |
| `0x01AFE9C0` | `scr_errorMessage` | 1024 bytes |

Script VM instance arrays (same strides as MP): `0x01AE96B4` / `0x01AF22F4` (stride `0x4620`),
`0x01AF22FC` (stride `0x201C`), `0x01AF6334` (stride `0x4320`, MP `0x01E97F34`).

## Imports

277 functions from 21 libraries — MP minus `cellHttp`, `cellSsl`, `cellRec` (theater video
recording) and `sceNpCommerce2` (in-game store). Everything else matches MP.
