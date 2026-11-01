#!/usr/bin/env python3
"""Status of the PS2Recomp shared bench lock on this box.

Reads the two lock slots, the waiting queue and the priority requests kept by the
fork's PS2Recomp/tools/bench_lock.sh (that file documents the protocol) and prints
who holds the bench, who is waiting, and why.  Read-only: it never takes, releases
or cleans anything, not even a stale entry.

  bench_status.py               the full status
  bench_status.py --short       one line per slot and waiter
  bench_status.py --json        the same data as JSON
  bench_status.py --watch [s]   refresh every s seconds (default 5)
  bench_status.py --procs-all   list every process of the ports, not a summary
  bench_status.py --no-procs    skip the process scan (one PowerShell call, ~2 s)

PS2X_BENCH_LOCK, PS2X_BENCH_LOCK2 and PS2X_BENCH_QUEUE override the paths, as in
the shell tool; the ask directory follows the first slot's path (.ask.d).
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

DEFAULT_LOCK = "D:/ps2recomp_bench.lock"
QUEUE_STALE = 60      # s without a refresh: bench_lock_queue_head drops the entry
ASK_LAPSE = 600       # s: a priority request lapses
ASK_COOLDOWN = 1800   # s: a port asks at most once every 30 min

# The ports of this box: the name they write into the lock, their checkout, and other
# spellings seen for them.  A name found in the lock that is not here is still shown.
PROJECTS = [
    ("tmb-recomp",    "D:/TMB_Recomp",       ("TMB", "tmb", "boubou-tmb", "TMB-Recomp")),
    ("tlotr-tta",     "D:/TLOTR_TTA_Recomp", ("TTA", "tlotr", "TLOTR-TTA")),
    ("JC2-Recomp",    "D:/JC2_Recomp",       ("JC2", "jc2", "jc2-recomp")),
    ("VP2S-Silmeria", "D:/VP2S_Recomp",      ("VP2S", "vp2s", "VP2S-Recomp", "Silmeria")),
]
RUNNER_NAMES = ("ps2entryrunner", "vp2s")      # the games themselves: what a slot is for
BUILD_NAMES = ("cmake", "ninja", "make", "c++", "g++", "gcc", "clang", "cc1plus", "cc1",
               "ld", "lld", "link", "cl", "ar", "ranlib", "cpp", "python",
               "objcopy", "objdump", "strip", "nm", "windres", "rc")
IGNORE_NAMES = ("claude", "powershell", "pwsh", "conhost", "windowsterminal", "explorer",
                "code", "rg", "grep", "findstr")

SLOT_RE = re.compile(r"^(\S+)\s+until\s+(\d{1,2}:\d{2})\s*(?:\((.*)\))?\s*$")
ENTRY_RE = re.compile(r"^(\d{20})-(.*)-(\d+)$")


# ---------------------------------------------------------------- paths & helpers

def lock_file():
    return os.environ.get("PS2X_BENCH_LOCK", DEFAULT_LOCK)


def lock_file2():
    first = lock_file()
    return os.environ.get("PS2X_BENCH_LOCK2", re.sub(r"\.lock$", "2.lock", first))


def queue_dir():
    return os.environ.get("PS2X_BENCH_QUEUE", re.sub(r"\.lock$", ".queue.d", lock_file()))


def ask_dir():
    return re.sub(r"\.lock$", ".ask.d", lock_file())


def read_text(path):
    try:
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8", "replace").replace("\r", "")
    except OSError:
        return None


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def ago(seconds):
    """A duration in words, for an age or a time left."""
    seconds = int(round(seconds))
    if seconds < 60:
        return "%d s" % seconds
    if seconds < 3600:
        return "%d min" % (seconds // 60)
    return "%d h %02d" % (seconds // 3600, (seconds % 3600) // 60)


def clock(stamp):
    return datetime.fromtimestamp(stamp).strftime("%H:%M:%S") if stamp else "?"


def port_project(name):
    """The checkout behind a port name, or None when it is not one of this box's."""
    if not name:
        return None
    low = name.lower()
    for port, path, alts in PROJECTS:
        if low == port.lower() or low in [alt.lower() for alt in alts]:
            return port, path
    return None


# ---------------------------------------------------------------- the two slots

def until_datetime(until, now):
    """The "until HH:MM" of a slot as a moment: the nearest one, before or after now."""
    hour, minute = (int(part) for part in until.split(":"))
    try:
        when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None
    if when - now < timedelta(hours=-12):
        when += timedelta(days=1)
    elif when - now > timedelta(hours=12):
        when -= timedelta(days=1)
    return when


def slot_is_free(content, now):
    """bench_lock_slot_is_free, as the shell computes it: empty, or past its HH:MM.

    The shell compares HHMM numbers, not minutes, and allows for a lock taken before
    midnight that ends after it; this follows it so the verdict matches the tool the
    ports actually run.
    """
    if content is None or not content.strip():
        return True
    found = re.search(r"until (\d+):(\d+)", content)
    if not found:
        return False
    until = int("%d%02d" % (int(found.group(1)), int(found.group(2))))
    hhmm = int(now.strftime("%H%M"))
    return hhmm > until and (hhmm - until) < 1200


def read_slot(index, path, now):
    content = read_text(path)
    slot = {
        "slot": index,
        "file": path,
        "exists": content is not None,
        "raw": (content or "").strip(),
        "port": None,
        "project": None,
        "until": None,
        "why": None,
        "written_at": mtime(path),
        "free": slot_is_free(content, now),
        "parsed": False,
        "seconds_left": None,
        "overdue_seconds": None,
    }
    line = next((one for one in (content or "").splitlines() if one.strip()), "")
    found = SLOT_RE.match(line.strip())
    if found:
        slot["parsed"] = True
        slot["port"] = found.group(1)
        slot["until"] = found.group(2)
        slot["why"] = (found.group(3) or "").strip() or None
        known = port_project(slot["port"])
        slot["project"] = known[1] if known else None
        when = until_datetime(slot["until"], now)
        if when:
            left = (when - now).total_seconds()
            if left >= 0:
                slot["seconds_left"] = left
            else:
                slot["overdue_seconds"] = -left
    slot["state"] = "free" if slot["free"] and not slot["raw"] else (
        "stale" if slot["free"] else "held")
    return slot


# ---------------------------------------------------------------- queue & priority

def read_asks(now_stamp):
    """The open priority requests, and when each port last asked for one."""
    asks, lasts = {}, {}
    directory = ask_dir()
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return asks, lasts
    for name in names:
        path = os.path.join(directory, name)
        stamp = mtime(path)
        if name.endswith(".ask"):
            body = (read_text(path) or "").strip()
            minutes, _, why = body.partition("|")
            age = now_stamp - stamp if stamp else None
            asks[name[:-4]] = {
                "port": name[:-4],
                "minutes": minutes.strip() or None,
                "why": why.strip() or None,
                "asked_at": stamp,
                "age_seconds": age,
                "lapses_in_seconds": None if age is None else max(0.0, ASK_LAPSE - age),
                "lapsed": age is not None and age > ASK_LAPSE,
            }
        elif name.endswith(".last"):
            age = now_stamp - stamp if stamp else None
            lasts[name[:-5]] = {
                "port": name[:-5],
                "asked_at": stamp,
                "age_seconds": age,
                "can_ask_in_seconds": None if age is None else max(0.0, ASK_COOLDOWN - age),
            }
    return asks, lasts


def read_queue(now_stamp, asks):
    """The waiters, oldest first, as bench_lock_queue_head orders them."""
    directory = queue_dir()
    waiters, other = [], []
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return waiters, other
    for name in names:
        path = os.path.join(directory, name)
        found = ENTRY_RE.match(name)
        if not found:
            other.append(name)
            continue
        stamp = mtime(path)
        arrived = int(found.group(1)) / 1e9
        port = found.group(2)
        known = port_project(port)
        refresh_age = now_stamp - stamp if stamp else None
        waiters.append({
            "entry": name,
            "port": port,
            "project": known[1] if known else None,
            "pid": int(found.group(3)),        # the waiting shell's bash pid, not a Windows one
            "arrived_at": arrived,
            "waiting_seconds": max(0.0, now_stamp - arrived),
            "refreshed_at": stamp,
            "refresh_age_seconds": refresh_age,
            "dead": refresh_age is not None and refresh_age > QUEUE_STALE,
            "ask": asks.get(port),
        })
    for position, waiter in enumerate(waiters, 1):
        waiter["position"] = position
    return waiters, other


# ---------------------------------------------------------------- the ports' tooling

def project_info():
    out = []
    for port, root, _alts in PROJECTS:
        fork = None
        for candidate in ("PS2Recomp/tools/bench_lock.sh", "external/PS2Recomp/tools/bench_lock.sh"):
            if os.path.isfile(os.path.join(root, candidate)):
                fork = os.path.join(root, candidate)
                break
        text = read_text(fork) if fork else ""
        wrappers = [name for name in ("bench_lock.sh", "bench_run.sh", "regress.sh")
                    if os.path.isfile(os.path.join(root, "scripts", name))]
        out.append({
            "port": port,
            "root": root,
            "present": os.path.isdir(root),
            "lock_tool": fork,
            "two_slots": bool(text and "bench_lock_file2" in text),
            "priority": bool(text and "bench_lock_ask_priority" in text),
            "announce_hook": os.path.isfile(os.path.join(root, "build", "announce.sh")),
            "wrappers": wrappers,
        })
    return out


# ---------------------------------------------------------------- what is running

PS_SCRIPT = r"""
$pat = $env:BENCH_PROC_PAT
Get-CimInstance Win32_Process |
  Where-Object { ($_.ExecutablePath -and $_.ExecutablePath -match $pat) -or
                 ($_.CommandLine -and $_.CommandLine -match $pat) } |
  Select-Object ProcessId, Name, ExecutablePath, CommandLine,
    @{n='Start';e={ if ($_.CreationDate) { $_.CreationDate.ToString('yyyy-MM-ddTHH:mm:ss') } }} |
  ConvertTo-Json -Depth 3 -Compress
"""


def hidden_window_flags():
    """Keep PowerShell from flashing a console: the GUI runs under pythonw, which has none,
    so without this every scan pops a window for a second."""
    if os.name != "nt":
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW   # SW_HIDE
    return {"startupinfo": info, "creationflags": 0x08000000}  # CREATE_NO_WINDOW


def scan_processes():
    """The ports' runners and builds, from one PowerShell call. None when it cannot run."""
    roots = [root for _port, root, _alts in PROJECTS]
    parts = [re.escape(os.path.basename(root)) for root in roots] + list(RUNNER_NAMES)
    env = dict(os.environ, BENCH_PROC_PAT="|".join(parts))
    try:
        done = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PS_SCRIPT],
            capture_output=True, text=True, timeout=60, env=env, **hidden_window_flags())
    except (OSError, subprocess.SubprocessError):
        return None
    body = (done.stdout or "").strip()
    if not body:
        return []
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = [data]
    out = []
    for item in data:
        path = item.get("ExecutablePath") or ""
        line = item.get("CommandLine") or ""
        name = (item.get("Name") or "").lower()
        stem = os.path.splitext(name)[0]
        if stem in IGNORE_NAMES:
            continue
        haystack = (path + " " + line).replace("\\", "/").lower()
        project = next((root for root in roots
                        if os.path.basename(root).lower() in haystack), None)
        if any(one in stem for one in RUNNER_NAMES):
            kind = "runner"
        elif stem in BUILD_NAMES:
            kind = "build"
        else:
            kind = "shell"            # bash, timeout, git, ... around the real work
        out.append({
            "pid": item.get("ProcessId"),
            "name": item.get("Name"),
            "path": path or None,
            "command": line or None,
            "started": item.get("Start"),
            "project": project,
            "kind": kind,
        })
    order = {"runner": 0, "build": 1, "shell": 2}
    out.sort(key=lambda proc: (order[proc["kind"]], proc["project"] or "~", proc["started"] or ""))
    return out


# ---------------------------------------------------------------- collect & render

def collect(with_procs=True):
    now = datetime.now()
    now_stamp = time.time()
    slots = [read_slot(1, lock_file(), now), read_slot(2, lock_file2(), now)]
    asks, lasts = read_asks(now_stamp)
    waiters, strays = read_queue(now_stamp, asks)
    holders = {slot["port"] for slot in slots if slot["state"] == "held" and slot["port"]}
    free = sum(1 for slot in slots if slot["free"])
    if free == 2:
        verdict = "free (both slots)"
    elif free == 1:
        verdict = "one slot free: a game run can start, a build or a timed run cannot"
    elif len(holders) == 1:
        verdict = "held ALONE by %s: nothing else should start" % next(iter(holders))
    else:
        verdict = "both slots taken: nothing else should start"
    return {
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "verdict": verdict,
        "slots_free": free,
        "alone": len(holders) == 1 and free == 0,
        "slots": slots,
        "queue": waiters,
        "queue_dir": queue_dir(),
        "queue_strays": strays,
        "asks": list(asks.values()),
        "ask_dir": ask_dir(),
        "ask_cooldowns": list(lasts.values()),
        "projects": project_info(),
        "processes": scan_processes() if with_procs else None,
    }


def who(port, project):
    if not port:
        return "-"
    return "%s (%s)" % (port, os.path.basename(project)) if project else "%s (unknown port)" % port


def label(project):
    """A project root as its directory name, for a process whose port is not written down."""
    return os.path.basename(project) if project else "(no port dir)"


def slot_line(slot):
    if slot["state"] == "free":
        return "  slot %d  FREE" % slot["slot"]
    head = "  slot %d  %-5s %s" % (slot["slot"], slot["state"].upper(),
                                   who(slot["port"], slot["project"]))
    if slot["until"]:
        if slot["seconds_left"] is not None:
            head += "  until %s (%s left)" % (slot["until"], ago(slot["seconds_left"]))
        elif slot["overdue_seconds"] is not None:
            head += "  until %s (%s ago)" % (slot["until"], ago(slot["overdue_seconds"]))
    if slot["written_at"]:
        head += "  taken %s" % clock(slot["written_at"])
    return head


def render(state, short=False, detail=False):
    out = []
    out.append("PS2Recomp bench lock - %s" % state["now"])
    out.append("  %s" % state["verdict"])
    out.append("")
    out.append("SLOTS  (%s, %s)" % (state["slots"][0]["file"], state["slots"][1]["file"]))
    for slot in state["slots"]:
        out.append(slot_line(slot))
        if slot["state"] == "stale":
            out.append("          stale: past its time, so the next waiter may take it over")
            out.append("          line: %s" % slot["raw"])
        elif slot["state"] == "held" and not short:
            out.append("          why:  %s" % (slot["why"] or "(no purpose given)"))
            if not slot["parsed"] and slot["raw"]:
                out.append("          line: %s  (not \"<port> until HH:MM (why)\")" % slot["raw"])
    if state["alone"]:
        out.append("  -> both slots are the same port's: it holds the bench alone "
                   "(a build or a timed run).")

    out.append("")
    queue = state["queue"]
    out.append("QUEUE  (%d waiting, %s)" % (len(queue), state["queue_dir"]))
    if not queue:
        out.append("  nobody waiting")
    for waiter in queue:
        line = "  %d. %-28s bash pid %-8s waiting %s (since %s)" % (
            waiter["position"], who(waiter["port"], waiter["project"]), waiter["pid"],
            ago(waiter["waiting_seconds"]), clock(waiter["arrived_at"]))
        if waiter["refresh_age_seconds"] is not None:
            line += "  refreshed %s ago" % ago(waiter["refresh_age_seconds"])
        out.append(line)
        if waiter["dead"]:
            out.append("      dropped next round: not refreshed for over %d s "
                       "(that shell is gone)" % QUEUE_STALE)
        ask = waiter["ask"]
        if ask and not short:
            out.append("      asks to pass: ~%s min - %s"
                       % (ask["minutes"] or "?", ask["why"] or "(no reason)"))
            if ask["lapses_in_seconds"] is not None:
                out.append("      asked %s ago, lapses in %s; only the ports above it "
                           "can let it pass"
                           % (ago(ask["age_seconds"]), ago(ask["lapses_in_seconds"])))
    for stray in state["queue_strays"]:
        out.append("  (stray file in the queue directory: %s)" % stray)

    waiting_ports = {waiter["port"] for waiter in queue}
    loose = [ask for ask in state["asks"] if ask["port"] not in waiting_ports]
    if not short and (loose or state["ask_cooldowns"]):
        out.append("")
        out.append("PRIORITY  (%s)" % state["ask_dir"])
        for ask in loose:
            out.append("  %s asks to pass but is not in the queue: ~%s min - %s%s"
                       % (ask["port"], ask["minutes"] or "?", ask["why"] or "(no reason)",
                          " [lapsed]" if ask["lapsed"] else ""))
        for last in state["ask_cooldowns"]:
            if last["can_ask_in_seconds"]:
                out.append("  %s asked %s ago: can ask again in %s"
                           % (last["port"], ago(last["age_seconds"]),
                              ago(last["can_ask_in_seconds"])))
            else:
                out.append("  %s last asked %s ago: may ask again"
                           % (last["port"], ago(last["age_seconds"])))

    procs = state["processes"]
    if procs is not None and not short:
        out.append("")
        out.append("RUNNING  (%d process%s of these ports)"
                   % (len(procs), "" if len(procs) == 1 else "es"))
        if not procs:
            out.append("  no runner, build or shell of these ports is running")
        runners = [proc for proc in procs if proc["kind"] == "runner"]
        for proc in runners:
            out.append("  runner  %-22s %-18s pid %-7s since %s"
                       % (proc["name"] or "?", label(proc["project"]),
                          proc["pid"], (proc["started"] or "?")[11:16] or "?"))
            if proc["path"]:
                out.append("      %s" % proc["path"])
        if procs and not runners:
            out.append("  no game runner is running")
        if detail:
            for proc in procs:
                if proc["kind"] == "runner":
                    continue
                out.append("  %-7s %-22s %-18s pid %-7s since %s"
                           % (proc["kind"], proc["name"] or "?", label(proc["project"]),
                              proc["pid"], (proc["started"] or "?")[11:16] or "?"))
        else:
            for kind in ("build", "shell"):
                group = [proc for proc in procs if proc["kind"] == kind]
                if not group:
                    continue
                per_project = {}
                for proc in group:
                    per_project.setdefault(label(proc["project"]), []).append(proc)
                for project in sorted(per_project):
                    mine = per_project[project]
                    names = sorted({proc["name"] or "?" for proc in mine})
                    oldest = min((proc["started"] or "~") for proc in mine)
                    out.append("  %-7s %-18s %d process%s (%s), oldest since %s"
                               % (kind, project, len(mine), "" if len(mine) == 1 else "es",
                                  ", ".join(names[:4]) + (", ..." if len(names) > 4 else ""),
                                  oldest[11:16] if oldest != "~" else "?"))
            out.append("  (--procs-all lists them one by one)")
    elif procs is None and not short:
        out.append("")
        out.append("RUNNING  (the process scan did not run: --no-procs, or no PowerShell)")

    if not short:
        out.append("")
        out.append("PORTS ON THIS BOX")
        for info in state["projects"]:
            bits = ["2 slots" if info["two_slots"] else "1 slot (old tool)",
                    "priority" if info["priority"] else "no priority",
                    "announces" if info["announce_hook"] else "no announce hook"]
            if info["wrappers"]:
                bits.append("scripts/" + ", scripts/".join(info["wrappers"]))
            out.append("  %-15s %-22s %s" % (info["port"], info["root"],
                                             "missing" if not info["present"]
                                             else "; ".join(bits)))
    return "\n".join(out)


def main(argv):
    short = "--short" in argv
    as_json = "--json" in argv
    detail = "--procs-all" in argv
    with_procs = "--no-procs" not in argv and not short  # --short does not print them
    watch = None
    if "--watch" in argv:
        index = argv.index("--watch")
        watch = 5.0
        if index + 1 < len(argv):
            try:
                watch = float(argv[index + 1])
            except ValueError:
                pass
    known = ("--short", "--json", "--watch", "--no-procs", "--procs-all")
    unknown = [one for one in argv[1:] if one.startswith("--") and one not in known]
    if unknown or "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 2 if unknown else 0
    while True:
        state = collect(with_procs)
        if as_json:
            print(json.dumps(state, indent=2, sort_keys=False))
        else:
            if watch:
                sys.stdout.write("\033[2J\033[H")
            print(render(state, short, detail))
        if not watch:
            return 0
        try:
            time.sleep(watch)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
