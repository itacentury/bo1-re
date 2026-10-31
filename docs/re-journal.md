# RE journal — peculiarities and pitfalls

Chronological notes from reversing the MP and SP/ZM EBOOTs (TU13). Each entry: what happened, why, and
what to do about it.

## Container / loading

1. **Fake-signed SELF, plain ELF inside.** Key revision `0x8000`, segments neither compressed
   nor encrypted; the whole ELF sits at `0x900`. My first extractor read the segment-info
   offset from the wrong SCE extended-header field (`0x58` instead of `0x48`) and the sub-segments
   (TLS/PROC_PARAM/PRX_PARAM) use `encrypted=0` rather than `2` — both now handled.
2. **Section names and comment are zeroed.** Only PT_LOAD data survived the retail →
   fake-signed rebuild. Sections had to be named from type/flags/content.
3. **rea rejects the SELF and the PPC64 ELF** ("unsupported ELF architecture"); it only admits
   ELF32 EM_PPC, raw-binary does not offer PowerPC and the GameCube DOL lane would pick a 32-bit
   Gekko language (no `ld`/`std`/`rldicl`). Fix: rewrite the headers to ELF32 (segments stay
   byte-identical; PS3 addresses are 32-bit) and set `REA_GHIDRA_LANGUAGE_ID=PowerPC:BE:64:64-32addr`.
   rea also cannot open a Ghidra `.gpr` project.
4. **Ghidra does not follow PS3 `.opd`.** 4558 functions reachable only via descriptors
   (command handlers, builtins, threads) were missing and could not be decompiled. Fix: synthetic
   `.symtab` with one `STT_FUNC` per OPD/`bl` target.

## Code patterns

5. **Strings are not in the TOC.** Code materialises addresses with `lis`+`addi` (sign-extended
   low half: `lis r4,0x8f; addi r4,r4,-0x56d0` → `0x8EA930`). The TOC (`0xB576E8`) is small and
   mostly used for a few globals.
6. **Float args consume GPR slots** (see 02-abi-quirks). Argument recovery that ignored this
   assigned `flags`/`desc` to the wrong registers.
7. **Non-volatile float constants.** Dvar registration functions load float defaults into
   `f21..f31` once at the start; a short backward scan missed them (`cg_fov` showed no default).
   Fix: simulate each function forward once and snapshot at every call site.
8. **`li -1; clrldi 33` = `INT_MAX`.** Integer maxima are built with a rotate/mask, not `lis/ori`;
   the simulator needs real `rldicl` semantics (first version reported `g_speed` max as `-1`).
9. **Stale register tracking produces false xrefs.** The first scanner kept `lis` values after
   the register was overwritten by unrelated instructions (a `lfs` got annotated as `'ire_smoke'`).
   The shared `ppcsim.step()` now clears every destination register it does not model.
10. **Tail calls hide function starts.** Small wrappers end with `b target` instead of `bl`;
    deriving function starts only from `bl` targets merged neighbouring functions (the dvar
    domain-text function looked like part of `0x4C7BF0`). Ghidra's function list is merged in.
11. **Server commands use a stub.** Every server command is also registered in the client command
    list with an empty `blr` handler (`0x3996D8`); the real handler is in the server list.
12. **Script getters take `(argIndex, inst)`, errors take `(inst, ...)`**, and some functions
    exist twice (generic + instance-0 specialised, e.g. `Scr_Error` / `0x5D1F60`).
13. **Error strings start with `0x15`.** Messages passed to `Com_Error` carry a leading `\x15`
    byte; substring searches must not anchor at the start.
14. **No `Com_Printf` hub.** No function with many `(channel, fmt)` calls exists; console prints
    seem compiled out in retail. `0x474578` (83 callers, takes a time stamp and a lock) looks like an
    event/log recorder rather than `Com_Printf` — unresolved.
15. **`'\n'` breaks `isprintable()`**: the first search for `Cbuf_AddText` (commands end in a
    newline) returned nothing because of the printable-string filter.
16. **Tool name clash**: a helper named `dis.py` shadowed Python's `dis` module and broke
    `capstone`'s import chain — renamed to `disasm.py`.

## SP/ZM EBOOT

17. **One EBOOT for campaign and Zombies.** `EBOOT_SP_ZM.BIN` (`online_tu13_sp_`) contains
    both modes; ZM is selected at runtime (`zombiemode`). Hence one `sp_zm` target, no `zm` folder.
18. **Section indices shift.** SP/ZM has 32 sections instead of 31: an extra executable
    section after PRX_PARAM (`0xA222E8`, 0x1CC bytes) issues raw `sc` 0x1E0/0x1E1
    (`sys_prx_load_module`/`sys_prx_start_module`). Section names therefore live per target in
    `target.json`; bounds the tools need are read from the ELF section headers.
19. **Masked-code matching works across EBOOTs.** Masking `bl`/`b` targets, `lis` immediates,
    TOC-relative displacements and every instruction the scanner resolved to an absolute address
    makes 5300 functions byte-identical between MP and SP/ZM. Struct offsets are *not* masked,
    so functions touching `gentity_t`/`gclient_t` fall out of the exact pass — that is wanted.
20. **Call-graph propagation lies sometimes.** Pairing callees by call-site position mapped
    MP `Player_GetMethod` onto SP's `Actor_GetMethod` (same shape, both called from the same
    dispatcher). ~20% of `callee` matches disagree on strings; they are transferred as `guess`, and
    lookup functions are now seeded from the table they reference.
21. **Different struct sizes, same code.** `gentity_t` `0x2F8` → `0x34C`, `gclient_t`
    `0x2A38` → `0x1D30`, `gentity_t.client` `+0x144` → `+0x13C`, `ps.weapon` `u16` → `u8`.
    The quickest proof is the same tiny builtin (`getplayerangles`) disassembled in both EBOOTs.
22. **No `Dvar_RegisterInt64` in SP/ZM.** The register wrappers are laid out in the same order
    as MP, with a gap where int64 would be.
23. **MP's script-entity/vehicle method table is split in SP/ZM** (291 + 108 entries), and SP/ZM
    adds sentient (threat bias) and two CSC tables. A data scan for `{name, opd[, x]}` runs found
    them; matching alone would not have.
24. **Remote inspect commands in both EBOOTs.** A table `{name, opd, opd}` with `peek`,
    `checksum`, `procaddr`, `section`, `dvar`, `dir`, `upload`, `mount` — missed in the MP pass
    because its third word is an OPD, not a developer flag. `peek` takes `%x %x`; the dispatcher
    runs in the per-controller online frame next to the ban check. Likely backend-driven integrity
    checks.
25. **Main-menu terminal is native.** The CIA computer (`dir`, `cat`, `zork`, `doa`, `3arc`…)
    is a `{name, handler}` table in SP/ZM (`0xA56AD8`).
26. **A duplicate spawn entry.** `spawn_manager` appears twice in the SP/ZM spawn table.

## Forum offsets (cross-check)

27. **Forum lists are mostly right but mislabel neighbours.** Checking a pasted MP list against
    strings and call shapes: `HudElem_Alloc` was `G_FindConfigstringIndex`, `PlayerCmd_SayAll`
    and `SayTeam` were swapped (the handler passing mode 1 sits under `sayteam` in the table),
    and "`R_AddCmdDrawText`" was the inner `AddBaseDrawTextCmd`, which takes an extra `w` float
    and cursor arguments — calling it with the forum prototype shifts every float by one FPR.
28. **…and caught two of mine.** `G_Spawn` was `0x5B90F8` (inferred from the `spawn()` builtin's
    call order, `likely`) — the real one references `"G_Spawn: no free entities"`. `G_SetModel`
    was its caller. The SP/ZM copy inherited the wrong `G_Spawn` through matching. Lesson: an
    error string beats call-order inference; never mark the latter above `likely`.
29. **`G_CallSpawn` vs `G_CallSpawnEntity`.** The function that looks up the spawn table reads
    `ent->classname` (`+0x164`) — that is `G_CallSpawnEntity`; `G_CallSpawn` reads `"classname"`
    from the level spawn vars.
30. **Xbox 360 addresses look like PS3 ones.** A dvar dump with `0x837xxxxx` pointers is from the
    360 (`0x82…`/`0x83…` image base) — useless as addresses, but it carries the dvar descriptions
    the PS3 build stripped, so they are merged by name.

31. **Second forum batch.** The community GSC/CSC dump matches `builtins.csv` 1:1 (1324 entries),
    which independently confirms the table extraction; its group names revealed the helicopter
    and vehicle blocks inside MP's combined method table. The FPS toggle and the JM RPC both patch
    the branch at `0x466298` in the UI debug overlay; forum button code reads a misaligned `u32`
    at `gclient+0x271` — the real fields are `+0x2914`/`+0x28FC`. `Dvar_GetBool` takes a
    `dvar_t *`, not a name (forum prototype wrong); `Dvar_GetString` does take a name.

## Stats (MP)

32. **Stats buffer from `statSetByName`.** `Cmd_statSetByName_f` gets its buffer from
    `LiveStats_GetStatsBuffer(ctrl, kind, check)` (`0x6B1E98`), a switch over six kinds:
    `statsBuffers` (`0x208B600`) + `ctrl * 0x26694` holds four `0x996D`-byte buffers at `+0`
    (kind 0/1, the live stats), `+0x996D` (2), `+0x132DA` (3) and `+0x1CC47` (5, also returned for
    kind 0 while `xblive_basictraining` is set); kind 4 is the global `0x2137C40`. It then calls
    `DDL_MoveToPath(&statsDDLRootState, …, 2, {"PlayerStatsList", name})` and `DDL_SetInt`.
33. **DDL data starts at buffer `+0x28`.** Every DDL accessor in `0x5E4…–0x5E7…` adds `0x140`
    bits to the member offset, and `DDL_SetInt` sets `buffer[8] |= 1` (dirty) — a 0x28-byte header.
    Fields are read/written with `ldbrx`/`stdbrx`: bit-packed **little-endian**, so a 32-bit stat
    is byte-swapped relative to a plain PPU load. `kills` (`playerstatslist[105]`, DDL `0x8E01`)
    is at `0x208B600 + 0x28 + 0x8E01 = 0x2094429` — inside the forum's `0x2094xxx` range.
    Offsets from `data/mp/stats_ddl.txt` (dumped on a PS3 running v1.13, so it matches this
    EBOOT) are generated into `include/bo1_mp/stats.h`
    (`BO1_STATS_ADDR(ctrl, BO1_STATS_playerstatslist_kills)`). The DDL (`0x9824` bytes incl.
    header) fits the `0x996D` buffer.

## Open questions

- Meaning of dvar flags `0x100`, `0x1000`, `0x2000`; field at `dvar_t+0x48`.
- `MSG_WriteBits` / `MSG_ReadBits` identification is pattern-based only.
- Exact size of `level_locals_t`, `MAX_GENTITIES` and the `g_clients` element count.
- Section 14 (`0x974100`, writable, 1.7 MB) — SPU images? Not analysed.
- SP/ZM: `G_InitGame` not located (MP anchor string is not referenced the same way);
  `CL_RegisterFont`, `Netchan_Transmit`, `SV_BuildClientSnapshot`, `SV_GetGuid`
  not matched yet.
- Stats: meaning of stats buffer kinds 2–4 (`stats_archive.ddl`? other-player stats?). The
  address chain (`0x2094429` = `kills`) is static only — confirm once at runtime with
  `statSetByName kills 1234` (expect bytes `D2 04 00 00`).
- Inspect commands: who sends them (Demonware task, server command?) and what `handler2` does.
- SP/ZM `level_locals_t` ends where `g_entities` begins (`level + 0x585C`) — verify.
