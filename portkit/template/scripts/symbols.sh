#!/usr/bin/env bash
# Rebuilds recomp/@PREFIX@_symbols.txt (@ELFNAME@ has no symbols) with BozoEngine's matcher, from reference executables
# that keep theirs and the names read by hand in recomp/@PREFIX@_symbols_reviewed.txt. Report: build/bozo/@PREFIX@_symbols_report.txt
# Usage: scripts/symbols.sh <reference.elf>...   (the map used Dark Cloud's SCUS_971.11, Twisted Metal: Black's
#        SCUS_971.01 and Onimusha: Warlords' SLUS_200.18: the player's own discs, never committed)
source "$(dirname "$0")/common.sh"
[ $# -gt 0 ] || { echo "usage: $0 <reference.elf>..."; exit 1; }
mkdir -p "$ROOT/build/bozo"
refs=()
for ref in "$@"; do refs+=(--ref "$ref"); done
python -I "$ROOT/BozoEngine/tools/symbolmap/bozo_symbolmap.py" engine-names "$ROOT/BozoEngine" "$ROOT/build/bozo/want.txt"
python -I "$ROOT/BozoEngine/tools/symbolmap/bozo_symbolmap.py" match "$ELF" "${refs[@]}" \
    --reviewed "$ROOT/recomp/@PREFIX@_symbols_reviewed.txt" --want "$ROOT/build/bozo/want.txt" \
    --out "$ROOT/recomp/@PREFIX@_symbols.txt" --report "$ROOT/build/bozo/@PREFIX@_symbols_report.txt"
head -2 "$ROOT/build/bozo/@PREFIX@_symbols_report.txt"
