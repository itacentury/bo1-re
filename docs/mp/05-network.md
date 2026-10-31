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

Host migration has its own `connectResponseMigration` path on the client.

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
