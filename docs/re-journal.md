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
34. **`0x46390` is `strcmp`, not `I_stricmp`.** It compares 8 bytes at a time with the
    `0x7F7F…` zero-byte trick and never folds case. The builtin lookups (`Scr_GetFunction`,
    `Player_GetMethod`, …) call it. The real `I_stricmp` is `0x4DD8C0`: it adds `0x20` to each byte
    in `'A'..'Z'` (`addi -0x41; cmplwi 0x19`) before comparing. `ClientCommand` (`0x2D6140`)
    matches `say`/`say_team`/`mr`/`callvote`/… with it, so `SAY` is chat as well.
39. **God mode / invisible custom classes are an invalid `body`.** Decoded from the
    unpacked IL of the CCAPI tool *Sakura Class Editor PS3* (`Class_Editor::button5_Click`).
    The button writes the single byte `0xC7` to `0x208B8F2 + n * 0x23` (MP custom class
    `n`, 0-based). `cacloadouts.customclass1.body` is DDL byte `0x2C9` bit 4 (DDL bit
    `0x164C`), 8 bits, so it straddles the high nibble of `0x208B8F1` and the low nibble of
    `0x208B8F2`. `head` follows 40 bits later (`0x1674`), and classes are 280 bits apart
    (`0x23` bytes). `prestigeclass1.body` is DDL byte `0x37C` bit 5 (`0x1BE5`), so the
    prestige classes are no longer nibble-aligned. In all 11 class dumps that ship with the
    tool, byte `0x208B8F2` is `0xC6` (body `0x62`); the tool's "Character" box writes body
    `0x62`–`0x66`. `0xC7` turns the low nibble 6 into 7, so body becomes **`0x72`**, which
    is not one of the body/head items. head is `0x61`, except `0x01` in class 3 of five
    dumps: the tool writes the primary as two whole bytes and clears the head's high nibble.
    That has no effect, because custom classes get `cac_head_type = get_default_head()`
    instead of the stats head.
    Stock `_class.gsc` (PC raw) reads it in `getCacDataGroup` with
    `getdstat("CacLoadouts", class, "body")`. The range is only checked by `assert`, then
    `level.tbl_armor[body]` (filled from the statsTable rows of group `body`/`head`) is
    undefined. `self.cac_body_type` is set from it when the loadout is given, and every
    `_armor.gsc` lookup (`armor_bullet`, `mobility`, `set_player_model`) indexes
    `level.cac_attributes[...][cac_body_type]`. The god mode (no damage) or invisible
    (no model) effect follows from that **(inferred from the scripts, not traced on a
    console)**. The host reads the *client's* stats it got over the network
    (`SV_ReceiveStats` → `client + 0x5A4F8`, read back by `getdstat`, see
    [mp/05-network.md](mp/05-network.md#client-stats-on-the-host)). The buffer has no data
    checksum, so the host can check and fix the value there: `body` of custom class `n`
    is at buffer bit `0x140 + 0x164C + n * 280`.
    Other writes of the same tool: Save/Load Classes reads or writes `0xC0` bytes at
    `0x208B8E0` (the 5 MP custom classes start at offset `0x11` of that block). "FFA TAC"
    writes `C4 04` at `0x208B8F7` (primary = `0x4C`, the tactical insertion). Its Combat
    Training addresses (`0x20A8538 + n * 0x23`) are unverified.

## HEN

35. **HEN files are retail-signed.** The HEN EBOOT and InfinityOps are compressed and encrypted
    (key revision 4), so `self2elf.py` rejects them. `rpcs3 --decrypt` decrypts them without separate keys. The
    decrypted EBOOT differs from the CFW one only in `sys_process_param.sdk_version`, and the SPRX code is
    identical (see [00-self-format.md](00-self-format.md#cfw-and-hen-builds)).

## Networking (MP)

36. **NetMsg lobby dispatch is name-keyed.** `NetMsg_Dispatch` (`0x203AD8`) walks
    `netMsgHandlerList` (`0xB31AF0`), a NUL-terminated array of `{const char *name,
    void **opd}` pairs, comparing the incoming message name (from `name+1`) against
    each with `I_stricmp` (case-insensitive), then calls the matched handler through
    its OPD descriptor via `bctrl`; an unregistered name is ignored (returns 0).
    There is **no numeric packet index** into the table, so no index-OOB /
    function-pointer hijack at the dispatch level. The handler names come from
    `builtins.csv` (the `NetMsg_` prefix default). The `opd` pointers land in the
    `.opd`-style descriptor region around `0xB47…`, where each descriptor is
    `{code_ptr, toc}` and `toc == 0xB576E8` (= `elf.toc`) for every entry — so the
    shared second word in those descriptors is just the module TOC, not a flag.

37. **`MSG_ReadString` (`0x3B1008`) and `MSG_ReadData` (`0x3B0230`) are bounded.**
    `MSG_ReadString(msg, out, size)` consumes bytes (advancing `msg->readcount`,
    limited by `msg->cursize`) and stores into `out` only while the written count is
    `< size`, then NUL-terminates. `MSG_ReadData(msg, dest, len)` checks
    `msg->readcount + len <= msg->cursize` (split messages use `splitSize` +0x18)
    before copying `len` bytes; it is source-bounded only, so dest safety rests on
    the caller's `len` (the NetMsg callers all pass constants, e.g. `8`/`0x24`).
    These are the readers behind the reliable-command and `NetMsg_*` string fields;
    they resolve part of the "MSG reads under-identified" open question (bit-level
    `MSG_ReadBits`/`MSG_WriteBits` are still pattern-based).

38. **Reliable client-command path.** `SV_ClientCommand` (`0x3E47B8`) reads the
    reliable sequence (`MSG_ReadBits`) and the command string (`MSG_ReadString` into
    a `0x400` stack buffer), drops stale/gapped sequences against
    `cl->reliableSequence` (`+0x5170`, `EXE_LOSTRELIABLECOMMANDS`), then
    `SV_ExecuteClientCommand` (`0x3E1B60`) tokenizes and walks the `svcmds` table
    (`0xB5DDA4`, first entry `"userinfo"`); a match is called via its function
    pointer, otherwise it falls through to game `ClientCommand` (`0x2D6140`).

40. **Stats packets after the mask is complete.** `SV_ReceiveStats` doesn't test the mask
    against `0x1FFFFFFFF`: it skips the packet only if the bits `0..count - 1` are all set,
    with `count` the second byte of the packet. A client that sends a count above 33 can
    overwrite any chunk `<= 0x20` after the host has checked or changed the buffer. A new
    client never inherits the old mask, `SV_DirectConnect` memsets the whole `client_t`
    (`0x3E66D4`).

## Freezes from other consoles (MP)

Found while building a host-side filter (Silinium's anti-freeze). The "Freeze PS3" options
of RTM tools use these.

41. **Two server commands index tables unchecked.** `CG_ServerCommand` (`0x164BB8`) passes
    `strtol(argv1, NULL, 10)` of `C <n>` to `BG_GetWeaponDef` (`0xC0A98`), which indexes
    `bg_weaponDefs` (`0xBD877C`) without a bounds check (the bound is `BG_GetNumWeapons`).
    A host sends `C 2026` or `C 44444444444` with `SV_GameSendServerCommand`. Configstrings
    (`d <index> <value>`) only get a `Com_Error` above `0xAC1` in
    `CL_CGameNeedsServerCommand` (`0x1A6F00`). That function tokenizes with
    `Cmd_TokenizeString` (`0x39B538`); for `d` it ends that and tokenizes again with
    `Cmd_TokenizeStringWithLimit(text, 3)` (`0x39B828`). `CG_ExecuteNewServerCommands`
    only calls `Cmd_EndTokenizedString` (`0x39A150`) when it returned 1. A filter that reads
    argv there has to tokenize the same way, or it checks a different argv than the game.
42. **Text icons carry a raw `Material *`.** A text icon is 8 bytes: `^`, type, width,
    height, `Material *`. The game builds them itself with a pointer into its own memory.
    The backend draw loop (`RB_DrawText`, `0x798490`) only takes types 1 and 2
    (`(b - 1) & 0xFF <= 1` at `0x799014`) and uses the pointer as is. Sent from another
    console (chat, a player name), the bytes after `^\x01` become a pointer to garbage,
    e.g. `^\x01xx\x12gfx_snow_sheet;` gives `0x12676678`, and every console that draws the text
    freezes. Routes: chat; a name in the userinfo, which the host stores
    (`SV_UserinfoChanged` `0x3E49D0`, `ClientUserinfoChanged` `0x2C2AE8` via `SV_GetUserinfo`
    `0x3EAB20`) and sends on to every client; in the lobby the host sends every member's name
    and clan tag on in `partystate` (`Party_WriteMembers` `0x204820`). The draw loop is only
    reached through render command 16 (`rb_renderCommandTable` `0xB446B0`, handler
    `0x79AB78`), which only `AddBaseDrawTextCmd` (`0x7538E8`) and `R_AddCmdDrawConsoleText`
    (`0x7533C0`) build. The other icon parsers (text width in `0x734A50`, the message window
    copy in `0x1AEAE0`) don't read the pointer. The kill feed (`CG_Obituary`, `0x1B0CD8`)
    stores the pointer as is.
43. **A real icon's `Material *` has a 0 high byte.** Materials live in the type 6 XAsset
    pool (`g_assetPools[6]` = `0xDD8C68`, eboot BSS). A filter can look a pointer up without
    `Material_RegisterHandle`, which would create a default entry for a missing name and
    wait for zone loads: `DB_FindXAssetHeader` (`0x2601A0`) hashes the name mod 30000 into
    `db_hashTable` (`0xF3E97C`, u16 entry indices, 0 ends a chain) over
    `g_assetEntryPool` (`0xEC8C74`, 16-byte `XAssetEntry`, next in chain at `+0xA`). Every
    zone load and unload goes through `DB_LoadXAssets` (`0x2615C0`). The unload runs on the
    calling thread before the load is handed off: a loop over the loaded zones calls the
    zone free `0x25E2C8` (no other caller) for each zone matching `freeFlags`, under
    critical section `0x44`. Only then are the names queued and the DB thread signaled
    (`0x3D4410`, `0x3D3FD8`, `0x3D6388`, no other caller). `sync` only selects the wait at
    the end. A cache of looked-up pointers therefore has to be cleared in a
    `DB_LoadXAssets` hook.

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
- Exact `body`/`head` item ids (statsTable rows of group `body`/`head`, i.e.
  `level.armor_index_start..end`). Only `0x61` (head) and `0x62`–`0x66` (body) have been
  seen so far. Also whether the prestige classes of a player who never prestiged are zero.
- Inspect commands: who sends them (Demonware task, server command?) and what `handler2` does.
- SP/ZM `level_locals_t` ends where `g_entities` begins (`level + 0x585C`) — verify.
- Size of the material pool (`0xDD8C68`); `0xB321C0` runs parallel to `g_assetPools` and may
  hold the pool sizes.
- Which thread draws the loading screen while `DB_LoadXAssets` runs (the remote screen
  update?).
- Names of the DB helpers `0x25E2C8` (zone free), `0x25E918` (links a default entry),
  `0x3D4410` / `0x3D3FD8` / `0x3D6388` (DB thread queue) and `0x265F60` (loadzone path).
- `XAssetEntry` field names other than `nextHash` are taken from the IW engine.
