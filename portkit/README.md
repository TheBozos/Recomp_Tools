# portkit: tools shared by the BozoEngine ports

Three small tools for the ports on this machine (Python 3, run from this folder). They only read the ports: nothing in a
port's own folder is changed, and nothing is pushed or created on GitHub.

## `new_port.py`: start a port with the team's layout

```bash
python new_port.py --title "Amplitude" --iso "D:/Amplitude (USA).iso" --prefix amp
```

Reads the serial, the executable's name and SHA-1 and the region from the disc (nothing is extracted to disk) and writes the
new port: `scripts/` (extract with the SHA-1 check, build, run, symbols, the shared-bench wrappers), `.gitignore`, MIT
`LICENSE`, a `CMakeLists.txt` skeleton that imports BozoEngine, a README in the team's format (banner first, the disc's
SHA-1, status table, build steps), `docs/RECOMP_NOTES.md`, the window's `.rc` + manifest, the BozoEngine submodule, and the
**icon and banner** from the team's `make_logo.py` (a starting variant: the clown with the game's name; theme it later). The
generated scripts are Amplitude's, byte for byte, with the game's names filled in. Refuses a non-empty destination. The
templates are in `template/` (placeholders `@TITLE@`, `@PREFIX@`, `@SERIAL@`, ...): edit them when the team's layout changes.

## `state_check.py`: do old save states still load, and run the same?

```bash
python state_check.py            # every registered state of every port with a built headless runner
python state_check.py --port TTA --state forest
python state_check.py --accept   # after reading why a hash changed: record the new baselines
python state_check.py --vault    # copy the registered states into D:/BozoStates/<port>/
```

Loads each state in the port's headless runner (hidden, muted, memory cards in a scratch folder), runs 120 frames after it and
compares the SHA-256 of the RAM dump with `baselines/<port>.json`. **FAIL**: the runner would not load it (an engine change
broke the state format: "section ... ends before its fields"). **CHANGED**: it loads but runs differently, which an engine
change may intend; read why, then `--accept`. States are registered in `ports.json`; the vault keeps a copy of each so a clean-up of
`build/` cannot lose them. The ports' states should be old ones, from before the last format changes: they are the point.

## `engine_check.py`: which engine is each port on, and does it still work on another?

```bash
python engine_check.py                              # each port's committed engine pin vs BozoEngine master
python engine_check.py --run master --port Onimusha # build it on master in a scratch worktree, then run its states
python engine_check.py --run <commit> --dry-run     # the steps only
python engine_check.py --clean                      # remove the scratch worktrees
```

`--run` makes a git worktree of the port under `D:/BozoScratch/statecheck/enginecheck/<port>` with the engine at REF (the game's
folder is a junction; the port's own folder is untouched) and runs the port's `scripts/build_runtime.sh` under its shared-bench
lock (`--alone`: other sessions' timed runs wait, as for any build), then the states of `state_check.py` on the new build. A full
build: minutes per port and all the CPU, so one port at a time.

## `ports.json`

One entry per port: its folder, the headless runner, the flags always passed, the build script, the folders to junction for a
scratch build (`link`) and the states to keep loading. A port whose runner is not built (`exe: null`) is skipped: fill it in when
it has one. `bench_status.py` (the folder above) shows who holds the shared bench.
