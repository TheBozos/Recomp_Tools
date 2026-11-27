#!/usr/bin/env bash
# Usage: scripts/extract_iso.sh <path-to-@TITLE_DASH@-@REGION_SHORT@.iso>
# Extracts the disc into game/ (the runtime mounts cdrom0: on the ELF's directory).
source "$(dirname "$0")/common.sh"
ISO="${1:-}"
[ -f "$ISO" ] || { echo "usage: $0 <iso>"; exit 1; }
mkdir -p "$GAME_DIR"
bsdtar -xf "$ISO" -C "$GAME_DIR"
chmod -R u+w "$GAME_DIR"
[ -f "$ELF" ] || { echo "ELF not found after extraction: $ELF (is this the @REGION@ @SERIAL@ disc?)"; exit 1; }
echo "Extracted to $GAME_DIR"
# The port is built against this disc's executable only.
want=@SHA1@
have=$(sha1sum "$ELF" | cut -d' ' -f1)
[ "$have" = "$want" ] || echo "warning: $ELF SHA-1 is $have, expected $want (another disc version?)"
