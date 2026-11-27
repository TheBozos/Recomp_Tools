#!/usr/bin/env bash
# Configure (prepares the resident image and the overlay modules from game/) and build @PREFIX@-headless and @EXE_NAME@.
# Usage: scripts/build_runtime.sh [extra cmake -D options]
source "$(dirname "$0")/common.sh"
cmake -S "$ROOT" -B "$GAME_BUILD" -G Ninja -DCMAKE_BUILD_TYPE="${BUILD_TYPE:-Release}" "$@"
cmake --build "$GAME_BUILD" -j "$JOBS"
