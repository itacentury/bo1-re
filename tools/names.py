"""Address -> name mapping from the data/ databases.

Curated names (functions.csv, globals.csv, imports.csv) win over names derived
automatically from handler tables (builtins.csv, commands.csv).
"""
import csv
import target as targets

BUILTIN_PREFIX = {
    "gsc_functions": "GScr_", "gsc_methods_player": "PlayerCmd_", "gsc_methods_hudelem": "HECmd_",
    "gsc_methods_scriptent_vehicle": "ScrCmd_", "gsc_methods_actor": "ActorCmd_", "csc_functions": "CScr_",
    "csc_methods": "CScrCmd_", "csc_methods_entity": "CScrEntCmd_", "spawn_functions": "SP_",
    "weapon_spawn_or_field_parsers": "WeapParse_", "ui_menu_script_commands": "UIScript_",
    "remote_inspect_commands": "InspectCmd_", "terminal_commands": "Terminal_", "gsc_methods_scriptent": "ScrCmd_",
    "gsc_methods_vehicle": "VehicleCmd_", "gsc_methods_sentient": "SentientCmd_", "csc_methods_player": "CScrPlayerCmd_",
    "csc_functions_sp": "CScr_",
}


def _rows(target, name):
    p = targets.get(target).data_dir / name
    return csv.DictReader(p.open()) if p.exists() else []


def auto_function_names(target: str = None) -> dict:
    names = {}
    for r in _rows(target, "commands.csv"):
        if r["handler"]:
            prefix = "SV_Cmd_" if r["kind"] == "server" else "Cmd_"
            names.setdefault(int(r["handler"], 16), f"{prefix}{r['name'].replace('+', 'plus_').replace('-', 'minus_')}_f")
    ranges = targets.get(target).builtin_prefix_ranges
    for r in _rows(target, "builtins.csv"):
        entry = int(r["entry"], 16)
        prefix = next((p for a, b, p in ranges if a <= entry <= b), BUILTIN_PREFIX.get(r["table"], "NetMsg_"))
        names.setdefault(int(r["handler"], 16), f"{prefix}{r['name']}")
        if r.get("handler2"):
            names.setdefault(int(r["handler2"], 16), f"{prefix}{r['name']}_2")
    return names


def curated_names(target: str = None) -> dict:
    names = {}
    for r in _rows(target, "imports.csv"):
        names[int(r["stub_code"], 16)] = r["name"]
    for r in _rows(target, "functions.csv"):
        names[int(r["addr"], 16)] = r["name"]
    for r in _rows(target, "globals.csv"):
        names[int(r["addr"], 16)] = r["name"]
    return names


def load_names(target: str = None) -> dict:
    names = auto_function_names(target)
    names.update(curated_names(target))
    return names
