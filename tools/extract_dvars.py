#!/usr/bin/env python3
"""Extract every statically registered dvar (name, type, defaults, limits, flags, dvar_t* global)."""
import csv
import re
import sys
from pathlib import Path

import ppcscan
import target as targets
from sim import Sim, s32

# type -> (gpr arg layout, fpr value count, fpr limit count); addresses come from target.json.
# GPR slots after floats are shifted because PPC64 floats also consume a GPR slot.
LAYOUTS = {
    "bool":   ({"value": 4, "flags": 5, "desc": 6}, 0, 0),
    "float":  ({"flags": 7, "desc": 8}, 1, 2),
    "vec2":   ({"flags": 8, "desc": 9}, 2, 2),
    "vec3":   ({"flags": 9, "desc": 10}, 3, 2),
    "vec4":   ({"flags": 10, "desc": None}, 4, 2),
    "int":    ({"value": 4, "min": 5, "max": 6, "flags": 7, "desc": 8}, 0, 0),
    "enum":   ({"enum_list": 4, "value": 5, "flags": 6, "desc": 7}, 0, 0),
    "string": ({"value": 4, "flags": 5, "desc": 6}, 0, 0),
    "color":  ({"flags": 8, "desc": 9}, 4, 0),
    "int64":  ({"value": 4, "min": 5, "max": 6, "flags": 7, "desc": 8}, 0, 0),
    "linear_color_rgb": ({"flags": 9, "desc": 10}, 3, 2),
    "color_xyz": ({"flags": 9, "desc": 10}, 3, 2),
}


# PS3 retail EBOOTs register dvars without descriptions; the texts come from an Xbox 360
# dvar dump ("0x… - Type: T - name" followed by indented description lines).
X360_DESCRIPTIONS = Path(__file__).resolve().parent.parent / "data" / "dvar_description_x360.txt"
X360_HEADER = re.compile(r"^0x[0-9A-Fa-f]+ - Type: \S+ - ([^\s=]*)")


def load_x360_descriptions():
    if not X360_DESCRIPTIONS.exists():
        return {}
    descs, name = {}, None
    for line in X360_DESCRIPTIONS.read_text(errors="replace").splitlines():
        m = X360_HEADER.match(line)
        if m:
            name = m.group(1).lower() or None
            continue
        text = " ".join(line.split())
        if name and text:
            descs[name] = f"{descs[name]} {text}" if name in descs else text
    return descs


def fmt_float(v):
    return "" if v is None else f"{v:g}"


def main():
    t = targets.get()
    REGISTER_FUNCS = {a: (tn, *LAYOUTS[tn]) for tn, a in t.dvar_register_funcs.items()}
    idx = ppcscan.load()
    sim = Sim(idx)
    elf = idx.elf

    def string(addr):
        if addr is None:
            return None
        addr &= 0xFFFFFFFF
        try:
            s = elf.cstr(addr)
            return s if s.isprintable() else None
        except (ValueError, UnicodeDecodeError):
            return None

    def enum_values(addr):
        vals = []
        try:
            while (p := elf.u32(addr + 4 * len(vals))) and len(vals) < 64:
                vals.append(string(p) or "?")
        except ValueError:
            return ""
        return "|".join(vals)

    states = sim.states_at([s for fn in REGISTER_FUNCS for s in idx.calls.get(fn, [])])
    rows, missing = [], 0
    for func, (tname, layout, nval, nlim) in REGISTER_FUNCS.items():
        for site in idx.calls.get(func, []):
            g, f = states[site]
            name = string(g.get(3))
            if name is None:
                missing += 1
                continue
            row = {"name": name, "type": tname, "register_site": f"0x{site:08X}",
                   "register_func": f"0x{func:08X}"}
            if nval:
                row["default"] = " ".join(fmt_float(f.get(i)) for i in range(1, nval + 1))
                if nlim:
                    row["min"] = fmt_float(f.get(nval + 1))
                    row["max"] = fmt_float(f.get(nval + 2))
            if "value" in layout:
                v = g.get(layout["value"])
                if tname == "string":
                    row["default"] = string(v) if v is not None else ""
                elif tname == "bool":
                    row["default"] = "" if v is None else str(int(bool(v & 0xFF)))
                else:
                    row["default"] = "" if v is None else str(s32(v) if tname != "int64" else v)
            for k in ("min", "max"):
                if k in layout:
                    v = g.get(layout[k])
                    row[k] = "" if v is None else str(s32(v) if tname != "int64" else v)
            if "enum_list" in layout:
                row["enum_values"] = enum_values(g[layout["enum_list"]] & 0xFFFFFFFF) if layout["enum_list"] in g else ""
            fl = g.get(layout["flags"])
            row["flags"] = "" if fl is None else f"0x{fl & 0xFFFFFFFF:X}"
            row["description"] = (string(g.get(layout["desc"])) or "") if layout["desc"] else ""
            ptr = sim.stored_result(site, g)
            row["dvar_ptr"] = f"0x{ptr:08X}" if ptr else ""
            rows.append(row)

    x360 = load_x360_descriptions()
    for row in rows:
        row["description"] = row["description"] or x360.get(row["name"].lower(), "")

    rows.sort(key=lambda r: (r["name"].lower(), r["register_site"]))
    fields = ["name", "type", "default", "min", "max", "enum_values", "flags", "dvar_ptr", "description",
              "register_func", "register_site"]
    out = sys.argv[1] if len(sys.argv) > 1 else t.data_dir / "dvars.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} dvar registrations, {missing} call sites without a constant name", file=sys.stderr)


if __name__ == "__main__":
    main()
