# 06 — Modding how-to

Examples use MP TU13 addresses; the SP/ZM values are in [sp_zm/03-engine-core.md](sp_zm/03-engine-core.md).
Addresses differ between the two EBOOTs and between title updates.

## Selecting the target

```sh
gcc ... -Iinclude -DBO1_TARGET_MP      # or -DBO1_TARGET_SP_ZM
```

`include/bo1/bo1.h` pulls in `include/bo1_<target>/`. Names are the same in both targets
wherever the function exists in both, so shared code needs no `#ifdef`s; struct field
offsets differ (`gentity_t.client` is `+0x144` in MP, `+0x13C` in SP/ZM) but the generated
structs handle that. Check `confidence` per target — SP/ZM entries matched from MP are
often one step lower.

## Calling a game function

PPU function pointers are pointers to OPDs. The generated header builds one per function:

```c
#include "bo1/bo1.h"

BO1_FN(Cbuf_AddText)(0, "fast_restart\n");
/* expands to ((Cbuf_AddText_t)&bo1_opd_Cbuf_AddText)(...), with
   bo1_opd_Cbuf_AddText = { 0x00399CC8, BO1_TOC } */
```

If the game itself has a descriptor (`BO1_GAME_OPD_<name>`), you may cast that address instead.
Float arguments: let the compiler handle them through the typedef — never pass floats as ints.

## Reading/writing dvars

```c
dvar_t *d = *(dvar_t **)BO1_DVAR_jump_height;   /* pointer stored by the register call */
d->current.value = 999.0f;                       /* bypasses domain checks and flags */
```

Writing `current` directly skips `Dvar_SetVariant` (no modified flag, no latch, no
cheat protection) — fine for local tweaks, wrong for dvars that must be networked.
`DVAR_CHEAT (0x80)` dvars are reset to their reset value while cheats are off
(`Dvar_RegisterNew`), so either clear the flag (`d->flags &= ~0x80`) or write after init.

## Entities and players

```c
gentity_t *ent = &((gentity_t *)BO1_g_entities)[clientNum];  /* stride 0x2F8 MP, 0x34C SP/ZM */
gclient_t *cl  = ent->client;                                /* +0x144 MP, +0x13C SP/ZM */
float *angles  = cl->ps_viewangles;                          /* +0x180 in both */
```

`structs.h` contains padded structs with `_Static_assert`s for the confirmed offsets, so the
same code is correct for both targets.

## Server commands to clients

`SV_GameSendServerCommand(-1, 0, "...")` reaches all clients. The game itself sends
`va("%c \"%s\"", 'g' /* bold */ or 'f', text)` for `iprintlnbold`/`iprintln`.
`'8' <name>` unlocks an achievement/trophy (`va("%c %s", '8', name)` in GSC `giveachievement`,
MP and SP/ZM; names like `SP_WIN_CUBA`, `DLC5_ZOM_FULLY_ARMED`).

## Hooking

1. **Table hooks (preferred)**: GSC builtins, spawn functions, console commands and party
   message handlers are called through OPD pointers stored in writable memory
   (`builtins.csv`: `entry`, `commands.csv`: `cmd_function`). Replace the pointer with your
   own OPD; keep the original to chain.
2. **Inline hooks**: patch the first instruction with a branch to a trampoline. Remember that
   code may be reached both by `bl` (direct) and via OPD (indirect); the TOC of your trampoline
   must be the game TOC `0x00B576E8` when you jump back.
3. Prefer `cmd_function_t` re-use: `Cmd_AddCommand` keeps your static struct — allocate it in
   your SPRX's data, not on the stack.

## RPC from a PC tool (MP, forum technique)

Forum tools call game functions from a PC by installing a small polling stub in code that runs
every frame:

- **JM variant**: flips the branch at `0x466298` in `UI_DrawDebugOverlay` (`0x465368`, the code
  behind the well-known FPS toggle `0x40 0x00` / `0x40 0x9A`) so the overlay path enters a stub
  written at `0x4667B4`.
- **Pattern variant**: searches `4BFFBE05 4BFFFC9x` from `0x7A21D4`; the hit + `0xC` is
  `0x7A21E0`, a render function called every frame, which is overwritten by the stub.

Both stubs read arguments from a block at `0x10050000` (outside the EBOOT image; r3–r11 from
`+0x0`, f1–f9 from `+0x24`, function address at `+0x48` (JM) or `+0x4C`, return value right after it) and call the **raw code address** with
`mtctr`/`bctrl` — no OPD, the game's TOC stays in r2, which is why game functions work.
Pass `gentity_t *` as `0x012AB290 + n * 0x2F8` (a common snippet has the typo `0x2F`).
Patched code is visible to the inspect `checksum` command.

## Checklist before trusting an address

- Check `confidence` in the CSV (`guess` = verify yourself).
- Check the version string (`online_tu13_mp_` / `online_tu13_sp_`) of the EBOOT you are patching.
- Code patched by a mod can be read back by the backend-driven inspect commands
  (`peek`/`checksum`, see [sp_zm/05-network.md](sp_zm/05-network.md#remote-inspect-commands)).
- Run `tools/validate_db.py` after edits.
