# Tooling

All tools live in `tools/` and run from there (`../.venv/bin/python <tool>`). `tools/build.sh
[mp|sp_zm ...]` runs the whole pipeline (default: both targets).

The target is selected with **`BO1_TARGET=mp|sp_zm`** (default `mp`). Section bounds, TOC and
the RW range come from the ELF; everything else an extractor needs (dvar register functions,
`Cmd_Add*`, builtin tables, section names) is in `data/<target>/target.json`.

| Tool | Purpose |
|---|---|
| `self2elf.py` | fake-signed SELF → ELF64 (verifies segments are plain and contiguous) |
| `target.py` | per-target config: `target.json` + layout derived from the ELF section headers |
| `elf64to32.py` | ELF64 → ELF32/EM_PPC (headers only); `--symbols data/<target>` appends `.symtab` and section names |
| `symelf.py` | `.symtab`/`.strtab`/`.shstrtab` writer used by `elf64to32.py` |
| `ps3elf.py` | ELF reader: segments, OPD, PRX_PARAM, imports |
| `nids.py` | resolve import NIDs: `sha1(name + suffix)[:4]` little-endian; candidates from RPCS3 `REG_FUNC`/`REG_FNID` sources + `data/nid_names_extra.txt` |
| `ppcsim.py` | one-instruction constant propagation (`lis/addi/ori/mr/rldicl/lfs/fmr/...`) |
| `ppcscan.py` | builds and caches the xref index (absolute refs + `bl` call graph + function starts) |
| `sim.py` | call-site argument recovery (whole-function forward simulation, snapshot per call site) |
| `argscan.py` | rank callees by constant string arguments — the main identification heuristic |
| `extract_dvars.py` / `extract_commands.py` / `extract_builtins.py` | regenerate the big tables |
| `extract_weapon_fields.py` | weapon def parse table (`cspField_t`) → `weapon_def_fields.csv` |
| `raw_extract.py` | optional: facts from the PC mod-tools rawfiles (see below) |
| `overview.py` | per-function summary of an address range (size, callers, callees, strings) |
| `strxref.py` | substring → strings → referencing functions |
| `disasm.py` | Capstone disassembly with string/name annotations |
| `db.py` | upsert curated functions/globals (`func`, `glob`, `bulk` TSV) |
| `names.py` | curated + auto-derived names |
| `gen_headers.py` | `include/bo1_<target>/*.h`, `include/bo1/{bo1,common}.h` |
| `match.py` | cross-target function matching (`--transfer` copies curated names/globals) |
| `validate_db.py` | consistency checks against the ELF |
| `sprx_path.py` | show/change the SPRX path a patched EBOOT loads at startup (max 39 chars; updates the ELF SHA-1 in the control info). In Git Bash set `MSYS_NO_PATHCONV=1`, or `/dev_hdd0/...` gets rewritten |

## Rawfiles (optional)

The PC mod tools ship the game's `raw/` folder (scripts, menus, weapon files, tables). The rawfiles are
Activision's and stay out of the repo. `raw_extract.py` derives facts from them into `data/`.
It is not part of `build.sh`, and every output is rewritten in full on each run:

```sh
export BO1_RAW="<steam>/steamapps/common/Call of Duty Black Ops/raw"
BO1_TARGET=mp ../.venv/bin/python raw_extract.py builtins    # data/<t>/builtins_script.csv
BO1_TARGET=mp ../.venv/bin/python raw_extract.py dvars       # data/<t>/script_dvars.csv
BO1_TARGET=mp ../.venv/bin/python raw_extract.py weapons     # data/<t>/weapon_fields.csv (run extract_weapon_fields.py first)
../.venv/bin/python raw_extract.py ui-defines                # data/ui_defines.csv
BO1_TARGET=mp ../.venv/bin/python raw_extract.py callbacks   # prints CodeCallback_* names
```

Files under `mp/`, `ui_mp/`, `mptype/`, `mpbody/`, `mphead/` count as MP, everything else as SP/ZM.
`codescripts/` and `common_scripts/` count for both. The GSC parser is a tokenizer, not a compiler:
`ent foo()` and `ent thread foo()` are methods, and calls that resolve to a script function (own file or
`#include`) are skipped. Menu dvar references come from regexes and are approximate. The rawfiles are
the PC build. Treat everything here as a hint for the PS3 EBOOT and check it there.

## rea / Ghidra

The rea MCP server (Ghidra 12.1.4 provider) only admits **ELF32 EM_PPC**, and selects the
language from `REA_GHIDRA_LANGUAGE_ID`. Configure the server with

```
REA_GHIDRA_LANGUAGE_ID=PowerPC:BE:64:64-32addr
```

and open `build/EBOOT_<T>.sym.elf32`. The synthetic symbols make Ghidra create the ~4.5k
functions that are only reachable through `.opd` (it does not parse PS3 OPDs itself) and
carry all database names. Full auto-analysis takes ~5 min (2/3 of it in "Decompiler Switch
Analysis"). rea sessions are ephemeral: names set with `set_addresses_names` vanish on close,
so put names into `data/` and regenerate the ELF instead.

Ghidra's own function list was exported once per target into `data/<target>/ghidra_functions.txt`
(`list_procedures` → `export_evidence_bundle`), and is merged into the scanner's function starts.

## Bringing up a new target (how SP/ZM was done)

1. `self2elf.py`, then `elf64to32.py --symbols data/<t>` with an almost empty `target.json`
   (only `binary`, `build`, `sections`) — symbols are then just OPD/`bl` entry points.
2. `nids.py` with the already resolved names of the other target as candidate list.
3. Open the symbol ELF in rea, export `list_procedures` → `ghidra_functions.txt`.
4. `match.py` against the known target; fill `target.json` from the matched anchors. Locate
   builtin tables by scanning data for `{name, opd[, x]}` runs and name them by entry-name
   overlap; take each table's lookup function from the data reference, not from the match.
5. Run the extractors, `match.py --transfer`, then verify and correct by hand.
