#!/usr/bin/env bash
# Rebuild every derived artifact from the EBOOTs: build.sh [mp|sp_zm ...] (default: all targets).
# Optional: RPCS3_MODULES=<rpcs3>/rpcs3/Emu/Cell/Modules re-resolves import NIDs.
set -euo pipefail
cd "$(dirname "$0")"
PY=../.venv/bin/python
mkdir -p ../build
TARGETS=("${@:-mp sp_zm}")

for T in ${TARGETS[@]}; do
    export BO1_TARGET=$T
    U=${T^^}
    echo "== $T"
    python3 -I self2elf.py ../EBOOT_$U.BIN ../build/EBOOT_$U.elf
    if [[ -n "${RPCS3_MODULES:-}" ]]; then
        $PY nids.py ../build/EBOOT_$U.elf ../data/$T/imports.csv ../data/nid_names_extra.txt \
            $(find "$RPCS3_MODULES" -name '*.cpp')
    fi
    $PY extract_dvars.py
    $PY extract_commands.py
    $PY extract_builtins.py
    $PY extract_weapon_fields.py
    $PY gen_headers.py
    $PY validate_db.py
    $PY elf64to32.py ../build/EBOOT_$U.elf ../build/EBOOT_$U.sym.elf32 --symbols ../data/$T
done
