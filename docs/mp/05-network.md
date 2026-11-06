# 05 — Network

## `msg_t` and bitstream

`msg_t` (from the field accesses of the MSG functions):

```
+0x00 int overflowed     +0x14 int cursize
+0x04 int readOnly?      +0x18 int splitSize
+0x08 char *data         +0x1C int readcount
+0x0C char *splitData    +0x20 int bit
+0x10 int maxsize        +0x24 int lastEntityRef?
```

| Address | Function | Confidence |
|---|---|---|
| `0x3AFE08` | `MSG_WriteByte` | confirmed |
| `0x3AFE48` | `MSG_WriteShort` | confirmed |
| `0x3AFE88` | `MSG_WriteLong` | confirmed |
| `0x3AF9F8` / `0x3AFA60` | `MSG_WriteBit0` / `MSG_WriteBit1` | likely |
| `0x3AF830` | `MSG_WriteBits` | guess |
| `0x3AFD58` | `MSG_ReadBit` | likely |
| `0x3AFEC8` | `MSG_ReadByte` | likely |
| `0x3B0008` | `MSG_ReadBits` | guess |
| `0x3C8660` | `Netchan_Transmit` | likely |

Reads support a split buffer (`data` + `splitData`, `readcount` across both).

## Connection flow

| Address | Function | Anchor |
|---|---|---|
| `0x1C7748` | `CL_CheckForResend` (guess) | sends `getchallenge` |
| `0x1CC320` | `CL_ConnectionlessPacket` | `challengeResponse`, `connectResponse`, `connectResponseMigration`, `disconnect` |
| `0x1D9640` | `CL_ParseServerMessage` | "Compressed msg overflow in CL_ParseServerMessage" |
| `0x3EE520` | `SV_ConnectionlessPacket` | `getchallenge`, `disconnect` |
| `0x3E1F68` | `SV_GetChallenge` | `challengeResponse %i` |
| `0x3E61F8` | `SV_DirectConnect` (guess) | sends `connectResponse` |
| `0x3F64E8` | `SV_BuildClientSnapshot` | "bad gEnt" |
| `0x3E95F0` | `SV_GameSendServerCommand` | `iprintlnbold` |
| `0x3E2828` | `SV_ReceiveStats` | OOB `stats`, answers `statresponse %lld` |
| `0x3E2700` | `SV_GetClientStatInt` | called by `getdstat`, "DDL: Could not get stat. Buffer error." |
| `0x3E49D0` | `SV_UserinfoChanged(cl)` | copies `name`/`clanAbbrev` from the userinfo (`client_t + 0x720`) |
| `0x3EAB20` | `SV_GetUserinfo(index, buf, size)` | the only userinfo reader of the game code (`ClientUserinfoChanged` `0x2C2AE8`, `ClientConnect` `0x2C2FB8`) |
| `0x1A6F00` | `CL_CGameNeedsServerCommand` | `clientConnections` (`0xD223C8`) + `lc * 0x35890`: sequence `+0x4348`, last executed `+0x434C`, 128 commands of `0x400` at `+0x4350` |

Host migration has its own `connectResponseMigration` path on the client.

## Client stats on the host

A client sends its stats buffer to the host as OOB `stats` packets: chunk index byte, chunk
count byte, then the data. `SV_ReceiveStats` looks the client up by address
(`SV_FindClientByAddress` `0x3EEAF8`) and copies each chunk into the client's own buffer.

| Field (`client_t`, stride `0x651C8`, array at `*(svs + 0x1C)`, `svs` = `0x1695280`) | Content |
|---|---|
| `+0x5A4F8` | stats buffer, `0x9968` bytes, same layout as the local one (DDL data at `+0x28`) |
| `+0x651B8` | `uint64` mask of the received chunks, complete = `0x1FFFFFFFF` (33 chunks) |
| `+0x651C0` | int, set once the buffer passed `DDL_ValidateBuffer` (`0x5E53B0`) |

- Chunk `i` lands at buffer `+ i * 0x4C6` with `min(0x4C6, 0x9968 - i * 0x4C6)` bytes. A packet
  is ignored if its chunk count is 0, if the mask bits `0..count - 1` are all set, or if the index
  is above `0x20`. The count is the client's, so once the mask is complete a packet with a count
  above 33 still overwrites a chunk (and sets its bit again). An incomplete mask accepts any chunk,
  also one that is already in.
- `SV_DirectConnect` clears the whole `client_t` (`memset(cl, 0, 0x651C8)` at `0x3E66D4`) before it
  uses a slot, for a free slot and for a reconnect from the same address (which first calls
  `0x3E3388`). The buffer and the mask of the previous client survive only until then.
- `svs.clients` is 0 while no server runs: `0x3EB7D8` allocates and clears the array, `0x3EA990`
  frees it and stores 0 (`0x3EAA0C`). `0x3EA990` is reached from `0x3ECE60` (`hostquit`,
  `EXE_DISCONNECTED`) via `0x1C7038`. These are the only stores to `svs + 0x1C`.
- `getdstat` on a player reads this buffer via `SV_GetClientStatInt` (also `0x3E2500` uint64,
  `0x3E2600` string). It returns 0 until the mask is complete and `client->state > 1`.
- `DDL_ValidateBuffer` only checks the buffer size and the DDL version in the header, there is
  no checksum over the data, so the host can change fields in place (re-journal entry 39).

## Party / lobby message handler tables

Several `{const char *name, opd_t *handler}` tables dispatch lobby/party messages by short
name (`builtins.csv`, tables `net_msg_handlers_a..e`):

| Address | Entries | Examples | Referenced by |
|---|---|---|---|
| `0xB31910` | 6 | `mstart` … `mstate` | `0x1B44A0`, `0x1D3FC0` |
| `0xB319F8` | 29 | `ph` … `profileack` | `0x1E5220`, `0x1EBC70` |
| `0xB31AE8` | 22 | `pha` … `pkick` | `0x203AD8` |
| `0xB31BA0` | 5 | `findbest` … `sessinfo` | `0x216368` |
| `0xB3ECC4` | 4 | `mrate` … `mtoack` | `0x3F1560` |

These are a natural place to filter malicious lobby packets (e.g. `pkick`).

The host sends the member list in `partystate` (`0x208DB0`, `%ipartystate`). It is written by
`Party_WriteMembers` (`0x204820`, only called from there): from a first member on until the
message is full, name with `MSG_WriteString`, clan tag with `MSG_WriteData`. Names and clan
tags of other members reach every client this way (see journal 42).

## Demonware

Demonware hosts: `cod7-ps3-{auth,lobby}.{prod,dev,cert}.demonware.net`,
`cod7-stun.{us,eu,jp,au}.demonware.net`. Demonware logging goes through `bdLogMessage`
(`0x8773E8`, 650 calls, channels `info/`, `warn/`, `err/` + `dwNet`, `core/bytebuffer` …),
which makes the `bd*` classes easy to map by their channel/function strings.

## Remote inspect commands

`0xB41D50`, 8 entries `{name, opd, opd}`: `peek`, `dvar`, `checksum`, `procaddr`, `section`,
`dir`, `upload`, `mount`; dispatcher `0x650DC0` (`InspectCmd_Dispatch`, guess). Same table as
in SP/ZM — the analysis and the anti-cheat hypothesis are in
[../sp_zm/05-network.md](../sp_zm/05-network.md#remote-inspect-commands).
