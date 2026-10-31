# 05 — Network (SP/ZM)

Only Zombies is played online (co-op over the same client/server code as MP). The
connection path and `msg_t` are the same as in [../mp/05-network.md](../mp/05-network.md).

| Address | Function |
|---|---|
| `0x5589F8` / `0x558A38` / `0x558A78` | `MSG_WriteByte` / `WriteShort` / `WriteLong` |
| `0x558AD0` | `MSG_ReadByte` |
| `0x557C58` / `0x558C10` | `MSG_WriteBits` / `MSG_ReadBits` (pattern-based, guess) |
| `0x4F18C0` | `CL_ParseServerMessage` |
| `0x4EB330` | `CL_ConnectionlessPacket` |
| `0x4E3780` | `CL_CheckForResend` |
| `0x4C9FE8` | `SV_ConnectionlessPacket` (getchallenge/connect/getinfo/getstatus) |
| `0x4C9D38` | `SVC_Status` — a separate function here, inlined in MP |
| `0x4BEEB0` | `SV_GetChallenge` |
| `0x4C0BC8` | `SV_DirectConnect` |
| `0x78E5C8` | `bdLogMessage` (Demonware) |

## Party handler tables

Only two of MP's five tables exist: `0xA3E0A8` (25 entries, lookup `0x4FD958`) and
`0xA3E178` (18 entries, lookup `0x511EC8`). Missing: `mhead/mstart/mstate/mdata`,
`findbest/migrateto/nominee` (host migration) and `mack/mhack/mrate/mtoack`.

## Remote inspect commands

`0xA3FEF0` (also in MP at `0xB41D50`): `peek`, `dvar`, `checksum`, `procaddr`, `section`,
`dir`, `upload`, `mount`, each with **two** handler OPDs (`handler`, `handler2` in
`builtins.csv`). `peek` parses `%x %x` (address, length) from the tokenized command into a
per-controller state block (stride `0x5A0` at `0x01B68700`). The dispatcher `0x5F3920` is driven
from the per-controller online frame `0x5F8988`, next to the ban check (`Cmd_banCheck_f`,
`EXE_DEMONWARE_DISCONNECT`). Working hypothesis: backend-driven memory/integrity inspection
(anti-cheat), **not** a developer console — anything a mod patches can be read back by it.
