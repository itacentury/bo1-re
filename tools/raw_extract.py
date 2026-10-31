#!/usr/bin/env python3
"""Derive facts from the PC mod-tools rawfiles (BO1_RAW=<game>/raw); the rawfiles themselves stay local.

  raw_extract.py builtins     # data/<target>/builtins_script.csv: call style + arg counts seen in GSC/CSC
  raw_extract.py dvars        # data/<target>/script_dvars.csv: dvars named by scripts and menus
  raw_extract.py weapons      # data/<target>/weapon_fields.csv: keys of the WEAPONFILE weapon defs
  raw_extract.py ui-defines   # data/ui_defines.csv: numeric #defines of ui/menudefinition.h
  raw_extract.py callbacks    # print the engine -> script CodeCallback_* entry points

The rawfiles are the PC build; everything here is a hint for the PS3 EBOOTs, not proof.
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import target as targets

ROOT = targets.ROOT
KEYWORDS = {"if", "else", "while", "for", "foreach", "in", "switch", "case", "default", "return", "wait",
            "thread", "childthread", "break", "continue", "waittillframeend", "true", "false", "undefined",
            "isdefined", "notify", "endon", "waittill", "waittillmatch", "size"}
# Methods are called on any expression, but these are only ever entities in practice.
TOKEN = re.compile(r'''
    (?P<ws>\s+|//[^\n]*|/\*.*?\*/)
  | (?P<str>&?"(?:\\.|[^"\\])*")
  | (?P<dev>/\#|\#/)
  | (?P<ident>[A-Za-z_][\w\\]*)
  | (?P<num>\d+(?:\.\d*)?|\.\d+)
  | (?P<op>::|\[\[|\]\]|==|!=|<=|>=|&&|\|\||\+\+|--|[-+*/%<>=!&|^~?:;,.()\[\]{}\#])
''', re.S | re.X)


def raw_root():
    p = os.environ.get("BO1_RAW")
    if not p or not Path(p).is_dir():
        raise SystemExit("set BO1_RAW to the game's raw/ directory (PC mod tools)")
    return Path(p)


def is_mp(rel):
    """Script/menu/weapon file belongs to the MP EBOOT; codescripts/common_scripts serve both."""
    parts = rel.lower().split("/")
    return "mp" in parts or "ui_mp" in parts or parts[0] in ("mptype", "mpbody", "mphead")


def in_target(rel, t):
    shared = rel.split("/")[0] in ("codescripts", "common_scripts")
    return shared or is_mp(rel) == (t.name == "mp")


def tokenize(text):
    """[(kind, value, line)] without whitespace/comments; strings keep their value."""
    out, line = [], 1
    for m in TOKEN.finditer(text):
        kind, val = m.lastgroup, m.group()
        if kind not in ("ws", "dev"):
            out.append((kind, val, line))
        line += val.count("\n")
    return out


def args_of(toks, i):
    """i points at '('; return (argument token lists, index after ')')."""
    depth, args, cur = 0, [], []
    for j in range(i, len(toks)):
        v = toks[j][1]
        if v in ("(", "[", "[[", "{"):
            depth += 1
            if depth == 1:
                continue
        elif v in (")", "]", "]]", "}"):
            depth -= 1
            if depth == 0:
                if cur or args:
                    args.append(cur)
                return args, j + 1
        elif v == "," and depth == 1:
            args.append(cur)
            cur = []
            continue
        cur.append(toks[j])
    return args, len(toks)


class Script:
    def __init__(self, rel, text):
        self.rel = rel
        self.toks = tokenize(text)
        self.includes = [tok[1] for tok in self.toks_after("#", "include")]
        self.defined = set()
        self.calls = []  # (name lower, is_method, args, line)
        self._scan()

    def toks_after(self, a, b):
        for i in range(len(self.toks) - 2):
            if self.toks[i][1] == a and self.toks[i + 1][1] == b:
                yield self.toks[i + 2]

    def _scan(self):
        toks, depth = self.toks, 0
        # ')' that closes an if/while/for/... condition ends a statement head, not a method target.
        control_close, opens = set(), []
        for i, (_, val, _) in enumerate(toks):
            if val == "(":
                opens.append(i)
            elif val == ")" and opens:
                o = opens.pop()
                if o and toks[o - 1][1].lower() in ("if", "while", "for", "foreach", "switch"):
                    control_close.add(i)
        for i, (kind, val, line) in enumerate(toks):
            if val == "{":
                depth += 1
            elif val == "}":
                depth -= 1
            if kind != "ident" or i + 1 >= len(toks) or toks[i + 1][1] != "(":
                continue
            name = val.lower()
            if depth == 0:
                self.defined.add(name)
                continue
            p = i - 1
            if p >= 0 and toks[p][1] in ("::", "#"):
                continue  # far call into another script / preprocessor
            while p >= 0 and toks[p][1] in ("thread", "childthread"):
                p -= 1
            prev = toks[p] if p >= 0 else ("op", ";", 0)
            is_method = ((prev[0] == "ident" and prev[1].lower() not in KEYWORDS)
                         or (prev[1] == ")" and p not in control_close) or prev[1] in ("]", "]]"))
            args, _ = args_of(toks, i + 1)
            self.calls.append((name, is_method, args, line))


def load_scripts(raw, t):
    scripts = {}
    for path in sorted(raw.rglob("*.[gc]sc")):
        rel = path.relative_to(raw).as_posix()
        if in_target(rel, t):
            scripts[rel] = Script(rel, path.read_text(errors="replace"))
    return scripts


def visible_defs(scripts):
    """Script functions an unqualified call in each file can resolve to (own + #include, not transitive)."""
    by_mod = {rel.rsplit(".", 1)[0].replace("/", "\\").lower(): s for rel, s in scripts.items()}
    out = {}
    for rel, s in scripts.items():
        names = set(s.defined)
        for inc in s.includes:
            if inc.lower() in by_mod:
                names |= by_mod[inc.lower()].defined
        out[rel] = names
    return out


def write_csv(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{path.relative_to(ROOT)}: {len(rows)} rows", file=sys.stderr)


def builtin_tables(t):
    tables = defaultdict(set)
    for r in csv.DictReader((t.data_dir / "builtins.csv").open()):
        if r["table"].startswith(("gsc_", "csc_")):
            tables[r["name"].lower()].add(r["table"])
    return tables


def cmd_builtins(raw, t):
    tables = builtin_tables(t)
    scripts = load_scripts(raw, t)
    visible = visible_defs(scripts)
    stats = defaultdict(lambda: {"func": 0, "method": 0, "argc": Counter(), "files": set(), "first": None})
    for rel, s in scripts.items():
        lang = rel.rsplit(".", 1)[1]
        for name, is_method, args, line in s.calls:
            if name in visible[rel] or not any(tb.startswith(lang) for tb in tables.get(name, ())):
                continue
            st = stats[name]
            st["method" if is_method else "func"] += 1
            st["argc"][len(args)] += 1
            st["files"].add(rel)
            st["first"] = st["first"] or f"{rel}:{line}"
    rows = []
    for name in sorted(tables):
        st = stats.get(name)
        if not st:
            rows.append({"name": name, "tables": "|".join(sorted(tables[name])), "uses": 0})
            continue
        argc = sorted(st["argc"])
        call = "both" if st["func"] and st["method"] else "method" if st["method"] else "func"
        rows.append({"name": name, "tables": "|".join(sorted(tables[name])), "call": call,
                     "argc_min": argc[0], "argc_max": argc[-1],
                     "argc_seen": "|".join(map(str, argc)), "uses": st["func"] + st["method"],
                     "files": len(st["files"]), "first_use": "raw:" + st["first"]})
    write_csv(t.data_dir / "builtins_script.csv",
              ["name", "tables", "call", "argc_min", "argc_max", "argc_seen", "uses", "files", "first_use"], rows)


# Builtins whose arguments at these positions are dvar names (setclientdvars takes name/value pairs).
DVAR_BUILTINS = {"getdvar": "r", "getdvarint": "r", "getdvarfloat": "r", "getdvarvector": "r",
                 "getdvarcolorred": "r", "getdvarcolorgreen": "r", "getdvarcolorblue": "r",
                 "getdvarcoloralpha": "r", "getdvarbool": "r", "getlocalclientdvar": "r",
                 "setdvar": "w", "setsaveddvar": "w", "setclientdvar": "w", "setclientdvars": "w*",
                 "setlocalclientdvar": "w", "makedvarserverinfo": "w", "setdvarbool": "w"}
MENU_DVAR = [re.compile(p, re.I) for p in (
    r'\bdvar\w*\s*\(\s*"([\w.]+)"',          # dvarString("x"), dvarInt("x"), ...
    r'\bdvar(?:test)?\s+"?([A-Za-z_][\w.]*)',  # dvar x / dvarTest x
    r'\b(?:set|seta|setdvar|toggle|setfromdvar)\s+"?([A-Za-z_][\w.]*)',
)]


def cmd_dvars(raw, t):
    engine = {r["name"].lower() for r in csv.DictReader((t.data_dir / "dvars.csv").open()) if r["name"]}
    st = defaultdict(lambda: {"reads": 0, "writes": 0, "menu_refs": 0, "files": set()})
    for rel, s in load_scripts(raw, t).items():
        for name, _, args, _ in s.calls:
            mode = DVAR_BUILTINS.get(name)
            if not mode:
                continue
            positions = range(0, len(args), 2) if mode == "w*" else range(min(1, len(args)))
            for p in positions:
                if len(args[p]) == 1 and args[p][0][0] == "str" and not args[p][0][1].startswith("&"):
                    d = st[args[p][0][1].strip('"').lower()]
                    d["writes" if mode[0] == "w" else "reads"] += 1
                    d["files"].add(rel)
    menu_dir = "ui_mp" if t.name == "mp" else "ui"
    for path in sorted((raw / menu_dir).rglob("*")):
        if path.suffix.lower() not in (".menu", ".inc", ".txt"):
            continue
        text = re.sub(r"//[^\n]*", "", path.read_text(errors="replace"))
        for rx in MENU_DVAR:
            for m in rx.finditer(text):
                d = st[m.group(1).lower()]
                d["menu_refs"] += 1
                d["files"].add(path.relative_to(raw).as_posix())
    # Menu regexes also catch "set" in other contexts; keep only names that look like dvars.
    rows = [{"name": n, "engine": int(n in engine), "reads": d["reads"], "writes": d["writes"],
             "menu_refs": d["menu_refs"], "files": len(d["files"])}
            for n, d in sorted(st.items())
            if n in engine or d["reads"] or d["writes"] or ("_" in n and d["menu_refs"] > 0)]
    write_csv(t.data_dir / "script_dvars.csv", ["name", "engine", "reads", "writes", "menu_refs", "files"], rows)


def value_kind(vals):
    if all(re.fullmatch(r"-?\d+", v) for v in vals):
        return "bool" if set(vals) <= {"0", "1"} else "int"
    if all(re.fullmatch(r"-?\d*\.?\d+(?:e-?\d+)?", v) for v in vals):
        return "float"
    return "string"


def cmd_weapons(raw, t):
    table = t.data_dir / "weapon_def_fields.csv"
    eboot = {r["name"].lower(): r for r in csv.DictReader(table.open())} if table.exists() else {}
    keys = defaultdict(Counter)
    files = 0
    for path in sorted((raw / "weapons" / ("mp" if t.name == "mp" else "sp")).iterdir()):
        text = path.read_text(errors="replace").strip()
        if not text.startswith("WEAPONFILE\\"):
            continue
        files += 1
        parts = text.split("\\")[1:]
        for k, v in zip(parts[::2], parts[1::2]):
            keys[k][v] += 1
    rows = []
    for k in sorted(keys, key=str.lower):
        vals = [v for v in keys[k] if v != ""]
        common = [v for v, _ in keys[k].most_common(8) if v != ""]
        e = eboot.get(k.lower(), {})
        rows.append({"key": k, "kind": value_kind(vals) if vals else "string",
                     "eboot_offset": e.get("offset", ""), "eboot_type": e.get("type_name", ""),
                     "files": sum(keys[k].values()), "distinct": len(keys[k]),
                     "values": "|".join(sorted(set(vals))) if 1 < len(set(vals)) <= 12 else "",
                     "example": common[0][:60].replace("\n", "\\n") if common else ""})
    missing = sum(1 for r in rows if not r["eboot_offset"])
    print(f"{files} weapon files" + (f", {missing} keys not in the EBOOT table" if eboot else ", no EBOOT table"),
          file=sys.stderr)
    write_csv(t.data_dir / "weapon_fields.csv",
              ["key", "kind", "eboot_offset", "eboot_type", "files", "distinct", "values", "example"], rows)


DEFINE = re.compile(r"^\s*#define\s+(\w+)\s+(\(?\s*-?(?:0x[0-9A-Fa-f]+|\d+(?:\.\d+)?)\s*\)?)\s*(?://\s*(.*))?$")


def define_group(name):
    for pfx in ("CG_SHOW_", "CG_HIDE_", "ITEM_TYPE_", "ITEM_ALIGN_", "ITEM_TEXTSTYLE_", "WINDOW_",
                "FEEDER_", "TEXTSIZE_", "UI_SHOW_", "UI_HIDE_"):
        if name.startswith(pfx):
            return pfx.rstrip("_")
    return name.split("_", 1)[0]


def cmd_ui_defines(raw, t):
    rows, cond = [], []
    for line in (raw / "ui" / "menudefinition.h").read_text(errors="replace").splitlines():
        s = line.strip()
        if s.startswith(("#ifdef", "#ifndef", "#if ")):
            cond.append(s)
        elif s.startswith("#endif") and cond:
            cond.pop()
        elif m := DEFINE.match(line):
            v = m.group(2).strip("() \t")
            v = str(int(v, 0)) if re.fullmatch(r"-?(0x[0-9A-Fa-f]+|\d+)", v) else v
            rows.append({"name": m.group(1), "value": v, "group": define_group(m.group(1)),
                         "condition": " && ".join(cond), "comment": (m.group(3) or "").strip()})
    write_csv(ROOT / "data" / "ui_defines.csv", ["name", "value", "group", "condition", "comment"], rows)


def cmd_callbacks(raw, t):
    found = defaultdict(set)
    for rel, s in load_scripts(raw, t).items():
        for kind, val, line in s.toks:
            if kind == "ident" and val.lower().startswith("codecallback_"):
                found[val].add(rel)
    for name in sorted(found, key=str.lower):
        print(f"{name}\t{', '.join(sorted(found[name]))}")


COMMANDS = {"builtins": cmd_builtins, "dvars": cmd_dvars, "weapons": cmd_weapons,
            "ui-defines": cmd_ui_defines, "callbacks": cmd_callbacks}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit(__doc__)
    COMMANDS[sys.argv[1]](raw_root(), targets.get())


if __name__ == "__main__":
    main()
