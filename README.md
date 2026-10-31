# bo1-re — Call of Duty: Black Ops (PS3) reverse-engineering database

Addresses, structures, dvars, commands, GSC builtins and notes for building mods for
**Black Ops 1 on PS3, title update 13 (v1.13)** — both EBOOTs.

| Target | File | SHA-1 | Internal name |
|---|---|---|---|
| `mp` | `EBOOT_MP.BIN` | `77a74cf2a14ac4029538536458fa8ce18d079fe9` | `t5mp_ps3f.self`, build tag `online_tu13_mp_` |
| `sp_zm` | `EBOOT_SP_ZM.BIN` | `94293f3f15bae74978d5801db341d89cf1e88f38` | `t5_ps3f.self`, build tag `online_tu13_sp_` |

Campaign and Zombies share one EBOOT, so there is one `sp_zm` target, not two: every address is
valid in both modes. The EBOOTs are shared by all regions (BLES01031–01035, BLES01105,
BLUS30591, NPUB20584). The binaries themselves are **not** in this repo (see `.gitignore`);
put them in the repo root.

## Layout

```
data/<target>/      single source of truth per EBOOT (CSV/JSON), see below
data/cross/         generated function matches between the targets
include/bo1/        bo1.h (target switch) + common.h (target-independent types)
include/bo1_<t>/    generated C headers per target (do not edit)
docs/               target-independent write-ups, RE journal
docs/mp/, sp_zm/    per-target memory map, engine core, script VM, network
tools/              extraction / analysis pipeline (Python), BO1_TARGET=mp|sp_zm
build/, analysis/   local outputs (ignored)
```

### Database (`data/<target>/`)

| File | MP | SP/ZM | Content |
|---|---|---|---|
| `target.json` | | | anchors the extractors need (register functions, tables) + section names |
| `functions.csv` | 107 | 104 | address, game OPD (if any), name, C prototype, subsystem, confidence, evidence |
| `globals.csv` | 14 | 10 | address, name, type, size, confidence, evidence |
| `structs.json` | | | struct layouts with per-field confidence |
| `dvars.csv` | 2766 | 2582 | every static dvar registration: type, default, min/max, enum values, flags, `dvar_t*` global, register site; descriptions from an Xbox 360 dump (2368 / 1985 matched by name) |
| `commands.csv` | 628 | 410 | console commands (client + server lists) with handler and `cmd_function_t` |
| `builtins.csv` | 1519 | 1696 | GSC/CSC functions & methods, spawn functions, UI menu-script commands, net handlers, inspect/terminal commands |
| `imports.csv` | 319 | 277 | every PRX import (library, NID, resolved name, stub) — 100% resolved |
| `ghidra_functions.txt` | 11149 | 14888 | Ghidra's own function starts (merged into the scanner) |
| `stats_ddl.txt` | 1053 | – | stats DDL layout (`ddl_mp/stats.ddl`): byte/bit offset into the DDL data, width, type, array, enum; plus 13 enums. Dumped at runtime on a PS3 running v1.13 (the DDL lives in the fastfiles, not the EBOOT); generated into `include/bo1_mp/stats.h` (buffer layout in `target.json` `stats`) |
| `weapon_def_fields.csv` | 748 | – | weapon def parse table (`cspField_t {name, offset, type}` at `target.json` `weapon_def_fields`): field offset and parse type (`CSPFT_*`, weapon-specific `WFT_*`); generated into `include/bo1_mp/weapon_fields.h`. SP/ZM: table not located yet |
| `builtins_script.csv` | 1166 | 1275 | *from the PC rawfiles*: per GSC/CSC builtin the call style (function/method) and argument counts seen in the mod-tools scripts, use count, first use |
| `script_dvars.csv` | 830 | 431 | *from the PC rawfiles*: dvars named by scripts (`getdvar*`/`setdvar`/…) and menus; `engine` = also in `dvars.csv`, else created by script/menu |
| `weapon_fields.csv` | 776 | 776 | *from the PC rawfiles*: every key of the `WEAPONFILE` weapon defs with value kind, example, and the matching EBOOT offset/type |

`data/ui_defines.csv` holds the 689 numeric `#define`s of the mod tools' `ui/menudefinition.h`
(ownerdraw `CG_*`/`UI_*`, `FEEDER_*`, `ITEM_TYPE_*`, …). It is generated into `include/bo1/ui_defines.h`.
Files marked *from the PC rawfiles* are derived with `tools/raw_extract.py` from the PC mod tools
(the rawfiles stay local, see [docs/tooling.md](docs/tooling.md#rawfiles-optional)). They are hints for
the PS3 build, not proof.

`data/cross/mp_sp_zm.csv` (8755 pairs) maps MP functions to SP/ZM ones with the match method
(`name`, `exact`, `strings`, `callee_exact`, `callee` — strongest first). SP/ZM entries
transferred from MP say so in their `notes`.

**Confidence** — `confirmed`: proven by string/xref/decompiled behaviour; `likely`: strong
pattern evidence; `guess`: plausible, verify before relying on it.

Functions not in `functions.csv` but in `commands.csv`/`builtins.csv` get automatic names
(`GScr_<name>`, `PlayerCmd_<name>`, `Cmd_<name>_f`, `SV_Cmd_<name>_f`, …) in the symbol export.

## Quick start

```sh
uv venv .venv && uv pip install --python .venv/bin/python -r tools/requirements.txt
tools/build.sh        # both targets: SELF -> ELF, extract tables, headers, validate, symbol ELF
tools/build.sh sp_zm  # one target
```

`build/EBOOT_<T>.sym.elf32` is an ELF32 with a synthetic `.symtab` carrying every name in
the database. Load it in Ghidra with language **`PowerPC:BE:64:64-32addr`** (or through the
rea MCP server, see [docs/tooling.md](docs/tooling.md)).

## Using the headers

Compile with `-Iinclude -DBO1_TARGET_MP` or `-DBO1_TARGET_SP_ZM`. Both targets use the same
names, so code that only uses names present in both builds for either EBOOT:

```c
#include "bo1/bo1.h"

void hello(void)
{
    BO1_FN(Cbuf_AddText)(0, "say hello\n");          /* call through a synthetic OPD */
    dvar_t *fov = *(dvar_t **)BO1_DVAR_cg_fov;        /* dvar_t* globals from dvars.csv */
    fov->current.value = 90.0f;
}
```

Read [docs/06-modding-howto.md](docs/06-modding-howto.md) before calling or hooking anything.

## Docs

- [00 SELF/ELF format](docs/00-self-format.md)
- [02 PPU ABI quirks](docs/02-abi-quirks.md)
- [06 Modding how-to](docs/06-modding-howto.md)
- [Tooling](docs/tooling.md)
- [RE journal](docs/re-journal.md) — pitfalls and peculiarities hit during the work

| | MP | SP/ZM |
|---|---|---|
| 01 Memory map | [mp](docs/mp/01-memory-map.md) | [sp_zm](docs/sp_zm/01-memory-map.md) |
| 03 Engine core — dvars, commands, game, render | [mp](docs/mp/03-engine-core.md) | [sp_zm](docs/sp_zm/03-engine-core.md) |
| 04 GSC/CSC VM | [mp](docs/mp/04-gsc-vm.md) | [sp_zm](docs/sp_zm/04-gsc-vm.md) |
| 05 Network | [mp](docs/mp/05-network.md) | [sp_zm](docs/sp_zm/05-network.md) |
| 07 Zombies and campaign specifics | | [sp_zm](docs/sp_zm/07-zombies.md) |
