# 07 — Zombies and campaign specifics

## Where Zombies lives

Almost nowhere in the EBOOT. Zombie-specific native code is limited to two GSC builtins
(`setzombiename`, `setzombieshrink`) and about 20 dvars:

- mode switches: `zombiemode`, `zombietron` (Dead Ops Arcade), `zombiemode_path_minz_bias`,
  `sv_zombietime`, `zombieStopSplitScreen`
- unlocks: `zombietron_discovered(_override)`, `zombiefive_discovered(_override)`,
  `zombiefive_norandomchar`
- presentation: `cg_showZombieMap`, `cg_showZombieControls`, `cg_ScoresColor_Zombie`,
  `compassObjectiveIcon{Width,Height}Zombie`, `r_zombieDisable{Earth,Slide}Effect`,
  `r_zombieNameAllow{Dev,Friends}List`, `allow_zombies_german`

Rounds, perks, the box, power-ups and so on are GSC scripts in the fastfiles — Zombies mods are
mostly script mods that call the builtins in [04-gsc-vm.md](04-gsc-vm.md). The string
`BlackOpsZombie` is referenced by `0x4C45A8`, which also reads `mapname`, `g_gametype` and
`protocol` (server/game info setup).

## Campaign-only native systems

- **AI**: actor (115) and sentient/threat-bias (11) method tables; `ai_*` dvars.
- **Save game**: UI commands `writeSave`, `savegameshow`, `setSaveExecOnSuccess`, server
  commands such as `update_sv_savegameavailable`, GSC `commitsave`.
- **Main-menu terminal** (the CIA computer with `dir`, `cat`, `zork`, `doa`, `3arc`, `alicia`…):
  `{name, handler}` table at `0xA56AD8`, 25 commands, lookup `0xCE720`. Handler names in the
  symbol ELF: `Terminal_<name>`.
- **Microfiche / credits** UI commands (`microfiche_start`, `credits_start`).

## Online pieces

No in-game store and no theater recording (`sceNpCommerce2`, `cellRec` are not imported).
See [05-network.md](05-network.md) for the co-op network path.
