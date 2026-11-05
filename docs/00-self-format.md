# 00 — SELF / ELF format of `EBOOT_MP.BIN`

## SCE header

| Offset | Value | Meaning |
|---|---|---|
| `0x00` | `SCE\0` | magic |
| `0x08` | `0x8000` | key revision → **fake-signed / debug SELF** |
| `0x0A` | `1` | header type SELF |
| `0x10` | `0x900` | header length = ELF offset inside the file |
| `0x18` | `0xB5AC60` | ELF size |
| `0x28` | `0x70` | app info offset |
| `0x30` | `0x90` | copy of the ELF header |
| `0x38` | `0xD0` | copy of the program headers |
| `0x40` | `0xB5ADA0` | section headers (= `0x900` + `e_shoff`) |
| `0x48` | `0x290` | segment info table (32 bytes per phdr) |

Segment info: PT_LOAD entries are `compressed=1` (no) and `encrypted=2` (no); the
TLS/PROC_PARAM/PRX_PARAM sub-segments use `encrypted=0` (not applicable). Consequence:
**the complete ELF is stored verbatim at `0x900`**. `tools/self2elf.py` checks this and cuts
it out — no keys, no scetool needed. A retail (encrypted, key revision ≠ `0x8000`) SELF must
be decrypted first.

## ELF

- `ELFCLASS64`, big-endian, `EI_OSABI = 0x66` (CELL LV2), `e_machine = 0x15` (PPC64), `ET_EXEC`.
- Entry `0x00B461E0` is **an OPD descriptor**, not code: `{func=0x00010230, toc=0x00B576E8}`.
- 8 program headers:

| # | Type | VAddr | FileSz | MemSz | Flags |
|---|---|---|---|---|---|
| 0 | LOAD | `0x00010000` | `0xB1AC68` | same | R-X |
| 1 | LOAD | `0x00B30000` | `0x0376BC` | `0x1C79798` | RW- |
| 2–4 | LOAD | 0 | 0 | 0 | empty placeholders |
| 5 | TLS | `0x00B507D4` | `0xD` | `0x2D0` | R |
| 6 | `0x60000001` PROC_PARAM | `0x00B2AC00` | `0x28` | | |
| 7 | `0x60000002` PRX_PARAM | `0x00B2AC28` | `0x40` | | |

For both PT_LOADs `vaddr = file_offset + 0x10000`.

### Zeroed non-loaded data

Everything outside PT_LOAD (`.shstrtab`, `.comment`, …) is **all zeroes** — the image was
rebuilt from a decrypted retail SELF. There are no section names and no symbols; the names
in [mp/01-memory-map.md](mp/01-memory-map.md) and [sp_zm/01-memory-map.md](sp_zm/01-memory-map.md) are reconstructed from type, flags, PRX_PARAM
pointers and content (names with `?` are content-based guesses).

### PROC_PARAM (`0xB2AC00`)

`size=0x24 magic=0x13BCC5F6 version=0x330000 sdk=0x340001 prio=0x3EA stack=0x18000
malloc_pagesize=0x100000 ppc_seg=0 crash_dump=0x3D2AD0`

### PRX_PARAM (`0xB2AC28`)

`magic=0x1B434CEC`, `libent` `0x8C8464..0x8C8464` (no exports), `libstub` `0x8C846C..0x8C88B8`
(25 import libraries, 319 functions, no variable imports).

## CFW and HEN builds

The SPRX-loader EBOOT and InfinityOps exist in a CFW and a PS3HEN build (local files, not in the repo). The CFW
EBOOT (the one this database is built from) is the retail game with a loader stub that calls `sys_prx_load_module` on `/dev_hdd0/tmp/InfinityOps.sprx` at startup (see `tools/sprx_path.py`). HEN does not
run fake-signed SELFs, so the HEN files are re-signed with retail keys.

| File | SHA-1 | Key rev | SELF type | App version | Segments | NPDRM |
|---|---|---|---|---|---|---|
| `EBOOT_MP.BIN` (CFW) | `77a74cf2a14ac4029538536458fa8ce18d079fe9` | `0x8000` | 4 (APP) | `0x0001000000000000` | plain | – |
| `EBOOT_MP.BIN` (HEN) | `97af351090234ac3a48ef41516e4925357a95c70` | `0x0004` | 8 (NPDRM) | `0x0001000000000000` | compressed, encrypted | free license, `JP9000-NPJA00001_00-0000000000000000` |
| `InfinityOps.sprx` (CFW) | `90fbecae4bc0d7ac3833ec5053dbcbc801ed56c6` | `0x8000` | 4 (APP) | `0x0001000000000000` | plain | – |
| `InfinityOps.sprx` (HEN) | `a5b91752589c37d4d71fc6dcb77d69087e4780ff` | `0x0004` | 4 (APP) | `0x0100000000000000` | compressed, encrypted | – |

All four use auth ID `1010000001000003` and vendor ID `01000002`. There is no HEN build of the SP/ZM EBOOT here.

**EBOOT.** The decrypted HEN EBOOT is the CFW ELF with one byte changed: `sys_process_param.sdk_version`
(`0xB2AC0C`) is `0x330001` instead of `0x340001`. Loader stub, path and all code are the same, so every address
in this database is valid for both. Whether HEN needs the lower SDK version is not verified; `tools/hen_eboot.py`
copies it.

**SPRX.** All segments of the HEN InfinityOps are byte-identical to the CFW build; only the symbol table is
stripped. It still writes game memory through syscalls 904/905 (`sys_dbg_read/write_process_memory`), so these
work on HEN, and a mod needs no HEN-specific code, only the other signature.

**Reproducing.** RPCS3 decrypts retail SELFs (`self2elf.py` refuses them):
`flatpak run --command=rpcs3 net.rpcs3.RPCS3 --decrypt <file>` writes `.elf` / `.prx` next to the input (add
`--filesystem=<dir>` for paths outside home; the flatpak mounts home read-only). Compare the result with the
`self2elf.py` output of the CFW file.

**Building.** `tools/hen_eboot.py` turns the CFW EBOOT into a HEN EBOOT with another SPRX path (see
[tooling.md](tooling.md)). An SPRX for HEN is signed with scetool as in the HEN InfinityOps:
`--sce-type=SELF --compress-data=TRUE --skip-sections=FALSE --self-add-shdrs=TRUE --key-revision=04
--self-auth-id=1010000001000003 --self-vendor-id=01000002 --self-type=APP --self-app-version=0001000000000000
--encrypt <prx> <sprx>`.
