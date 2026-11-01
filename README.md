# Recomp tools

## `bench_gui.pyw` — la petite fenêtre

Double-clic sur `bench-gui.vbs` — c'est le lanceur sans aucun clignotement de console ;
`bench-gui.cmd` fait la même chose mais montre un `cmd` une seconde au démarrage, et
`pythonw bench_gui.pyw [secondes]` la lance à la main (l'argument est l'intervalle de
relecture des locks). Fenêtre toujours au-dessus — case
« au-dessus » pour la laisser derrière — avec le verdict et sa pastille de couleur, les
deux slots (port, `until`, temps restant, heure de prise, *why* complet, `PÉRIMÉ` en
orange quand le slot a dépassé son heure), la file d'attente avec les demandes de
priorité, et les runners qui tournent. Double-clic sur une ligne : ouvre le dossier du
projet. Elle lit les locks toutes les 2 s et relance le scan des process toutes les 15 s
sur un thread à part, pour ne jamais bloquer l'affichage ; elle réutilise la lecture de
`bench_status.py` et reste en lecture seule. Le scan passe par PowerShell, lancé avec
`CREATE_NO_WINDOW` (`hidden_window_flags()`) : sans ça, `pythonw` n'ayant pas de console,
chaque scan en ouvrait une à l'écran toutes les 15 s.

## `bench_status.py` — who holds the shared bench

The PS2Recomp ports on this box (TMB, TTA, JC2, VP2S, and any other that joins) share one
bench through the lock that the fork's `PS2Recomp/tools/bench_lock.sh` keeps. This prints
its whole state, and nothing else: it is read-only, it never takes, releases or cleans a
slot, a queue entry or a priority request.

```bash
bench-status.cmd              # from PowerShell or cmd (bench-watch.cmd: refreshes, double-click it)
./bench-status                # from Git Bash / MSYS2 / Linux
python -I bench_status.py     # directly
```

| flag | what it does |
| --- | --- |
| `--short` | one line per slot and waiter, no processes, no port list |
| `--json` | the same data as JSON, for a script |
| `--watch [s]` | redraw every `s` seconds (default 5) |
| `--procs-all` | every matching process instead of a count per project |
| `--no-procs` | skip the process scan (one PowerShell call, ~2 s) |

`PS2X_BENCH_LOCK`, `PS2X_BENCH_LOCK2` and `PS2X_BENCH_QUEUE` override the paths, as in the
shell tool; the ask directory follows the first slot's path (`.ask.d`).

### What it shows, and what each part means

- **Slots** — `D:/ps2recomp_bench.lock` and `D:/ps2recomp_bench2.lock`, one line each,
  `<port> until HH:MM (<why>)`; empty means free. A game run takes one slot, so two games
  can run at once; a build or a timed measurement takes the bench **alone** (both slots),
  and the tool says so when one port holds both. Per slot it prints the port, which
  checkout that is, the `until`, the time left, when the line was written, and the full
  *why*.
  A slot past its `until` is **STALE**: the protocol lets the next waiter take it over (a
  crashed run must not block the others), so it counts as free — the verdict line on top
  says how much of the bench is actually free.
- **Queue** — `D:/ps2recomp_bench.queue.d`, one file per waiter named
  `<arrival, ns>-<port>-<pid>`, so the order shown is the order in which they will get the
  lock. A waiter refreshes its entry while it waits; one not refreshed for over 60 s
  belongs to a shell that died and is flagged as dropped next round. The pid is the
  waiting bash's own pid (an MSYS pid, not a Windows one), so it does not match the
  Windows pids in **RUNNING**.
- **Priority** — `D:/ps2recomp_bench.ask.d`. A waiter can ask the ports ahead of it to let
  it pass, with how long it needs and why (`bench_lock_ask_priority`); only those ports can
  let it (`bench_lock_yield`), silence keeps the order, and the request lapses after
  10 minutes. The tool prints each open request under its waiter, how long ago it was made,
  when it lapses, plus the 30-minute cooldown of each port that asked recently.
- **Running** — the ports' own processes, from one `Get-CimInstance Win32_Process` call:
  every game runner in full (`ps2EntryRunner`, `vp2s`), then builds and shells as a count
  per project. A runner with no slot, or a held slot with no runner, is worth a look.
- **Ports on this box** — each port's checkout and what its copy of the lock tool can do:
  two slots or only the first one (an older fork), priority requests or not, and whether
  it has a `build/announce.sh` hook to post its takes and releases to the c2c f2f lane.
  Ports differ here, and that explains behaviour: a port whose fork predates the second
  slot only ever sees slot 1.

The port names are mapped to checkouts by the `PROJECTS` table at the top of
`bench_status.py` — add a line there when a port joins the box; an unmapped name still
shows up, marked `(unknown port)`.
