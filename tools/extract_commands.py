#!/usr/bin/env python3
"""Extract console commands from Cmd_AddCommand (client list) and Cmd_AddServerCommand (server list)."""
import csv
import sys

import ppcscan
import target as targets
from sim import Sim


def main():
    t = targets.get()
    CMD_ADD_COMMAND = t.anchor("Cmd_AddCommand")
    CMD_ADD_SERVER_COMMAND = t.anchor("Cmd_AddServerCommand")
    # Server commands are also added to the client list with this empty stub as handler.
    CMD_STUB = t.anchor("Cmd_ServerCommandStub")
    idx = ppcscan.load()
    elf = idx.elf
    kinds = {s: "server" for s in idx.calls.get(CMD_ADD_SERVER_COMMAND, [])}
    kinds.update({s: "client" for s in idx.calls[CMD_ADD_COMMAND]})
    states = Sim(idx).states_at(list(kinds))
    rows = []
    for site, (g, _) in sorted(states.items()):
        name_ptr, opd, alloc = (g.get(r) for r in (3, 4, 5))
        try:
            name = elf.cstr(name_ptr & 0xFFFFFFFF) if name_ptr is not None else ""
        except ValueError:
            name = ""
        handler = elf.u32(opd & 0xFFFFFFFF) if opd else None
        if handler == CMD_STUB:
            handler = None  # real handler lives in the server command list
        rows.append({"name": name, "kind": kinds[site], "handler": f"0x{handler:08X}" if handler else "",
                     "handler_opd": f"0x{opd & 0xFFFFFFFF:08X}" if opd is not None else "",
                     "cmd_function": f"0x{alloc & 0xFFFFFFFF:08X}" if alloc is not None else "",
                     "register_site": f"0x{site:08X}",
                     "register_func": f"0x{idx.func_of(site):08X}"})
    rows.sort(key=lambda r: (r["name"].lower(), r["kind"], r["register_site"]))
    out = sys.argv[1] if len(sys.argv) > 1 else t.data_dir / "commands.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} commands, {sum(1 for r in rows if not r['name'])} without constant name", file=sys.stderr)


if __name__ == "__main__":
    main()
