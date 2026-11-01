#!/usr/bin/env pythonw
"""Petite fenetre de veille sur le bench lock partage des ports PS2Recomp.

Meme etat que bench_status.py (elle en reutilise la lecture) : les deux slots avec
leur why, la file d'attente, les demandes de priorite et les runners qui tournent.
En lecture seule : elle ne prend, ne libere et ne nettoie jamais rien.

  pythonw bench_gui.pyw            la fenetre (bench-gui.cmd fait pareil au double-clic)
  pythonw bench_gui.pyw 3          intervalle de rafraichissement des locks, en secondes

Les fichiers de lock se lisent instantanement, donc la fenetre les relit toutes les
2 s sur son propre thread ; le scan des process passe par PowerShell (~2 s), donc il
tourne a part toutes les 15 s et la fenetre affiche le dernier connu.
"""

import importlib.util
import os
import subprocess
import sys
import threading
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK_EVERY = 2.0      # s entre deux lectures des locks
PROC_EVERY = 15.0     # s entre deux scans de process

BG = "#1b1d22"
BG_CARD = "#23262d"
FG = "#e6e6e6"
DIM = "#8a8f98"
GREEN = "#55c57a"
ORANGE = "#ffb04c"
RED = "#ef5f5f"
BLUE = "#6fb4ff"

MONO = ("Consolas", 9)
MONO_B = ("Consolas", 9, "bold")
UI = ("Segoe UI", 9)
UI_B = ("Segoe UI", 13, "bold")


def load_status():
    """bench_status.py, a cote de ce fichier : la GUI n'est qu'un affichage de plus."""
    path = os.path.join(HERE, "bench_status.py")
    spec = importlib.util.spec_from_file_location("bench_status", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = load_status()


def open_folder(path):
    if path and os.path.isdir(path):
        subprocess.Popen(["explorer", os.path.normpath(path)], **bench.hidden_window_flags())


class Section(tk.Frame):
    """Un bloc titre + lignes, reconstruit seulement quand son contenu change."""

    def __init__(self, parent, title):
        super().__init__(parent, bg=BG_CARD)
        self.title = tk.Label(self, text=title, font=("Segoe UI", 8, "bold"), fg=DIM,
                              bg=BG_CARD, anchor="w")
        self.title.pack(fill="x", padx=10, pady=(8, 2))
        self.body = tk.Frame(self, bg=BG_CARD)
        self.body.pack(fill="x", padx=0, pady=(0, 8))
        self.signature = None

    def set_title(self, text):
        self.title.configure(text=text)

    def rows(self, rows):
        """rows : liste de (texte, couleur, indentation, gras, dossier a ouvrir)."""
        signature = repr(rows)
        if signature == self.signature:
            return
        self.signature = signature
        for child in self.body.winfo_children():
            child.destroy()
        for text, color, indent, bold, folder in rows:
            label = tk.Label(self.body, text=text, font=MONO_B if bold else MONO, fg=color,
                             bg=BG_CARD, anchor="w", justify="left", wraplength=430)
            label.pack(fill="x", padx=(10 + indent * 12, 10))
            if folder:
                label.configure(cursor="hand2")
                label.bind("<Double-Button-1>", lambda _event, path=folder: open_folder(path))


class Window:
    def __init__(self, root, lock_every):
        self.root = root
        self.lock_every = lock_every
        self.procs = None            # dernier scan de process, pose par le thread
        self.state = None
        self.error = None
        self.updated = None
        self.lock_thread_state = None

        root.title("Bench lock")
        root.configure(bg=BG)
        root.geometry("480x600")
        root.minsize(420, 320)
        root.attributes("-topmost", True)

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=12, pady=(10, 6))
        self.dot = tk.Canvas(head, width=14, height=14, bg=BG, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.dot_shape = self.dot.create_oval(1, 1, 13, 13, fill=DIM, outline="")
        self.verdict = tk.Label(head, text="lecture...", font=UI_B, fg=FG, bg=BG,
                                anchor="w", justify="left", wraplength=400)
        self.verdict.pack(side="left", fill="x", expand=True)

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        self.slots = Section(body, "SLOTS")
        self.slots.pack(fill="x", pady=(0, 8))
        self.queue = Section(body, "FILE D'ATTENTE")
        self.queue.pack(fill="x", pady=(0, 8))
        self.running = Section(body, "CE QUI TOURNE")
        self.running.pack(fill="x", pady=(0, 8))

        foot = tk.Frame(root, bg=BG)
        foot.pack(fill="x", padx=12, pady=(0, 10))
        self.stamp = tk.Label(foot, text="", font=UI, fg=DIM, bg=BG, anchor="w")
        self.stamp.pack(side="left")
        tk.Button(foot, text="Rafraichir", font=UI, command=self.refresh_now,
                  bg=BG_CARD, fg=FG, activebackground=BG_CARD, activeforeground=BLUE,
                  relief="flat", padx=8).pack(side="right")
        self.topmost = tk.BooleanVar(value=True)
        tk.Checkbutton(foot, text="au-dessus", font=UI, variable=self.topmost,
                       command=self.set_topmost, bg=BG, fg=DIM, selectcolor=BG_CARD,
                       activebackground=BG, activeforeground=FG, relief="flat",
                       highlightthickness=0).pack(side="right", padx=6)

        threading.Thread(target=self.lock_loop, daemon=True).start()
        threading.Thread(target=self.proc_loop, daemon=True).start()
        self.draw()

    # ------------------------------------------------------------------ lecture

    def lock_loop(self):
        while True:
            try:
                state = bench.collect(with_procs=False)
                self.error = None
            except Exception as problem:           # un lock illisible ne doit pas tuer la fenetre
                state, self.error = None, str(problem)
            if state:
                self.state = state
                self.updated = time.time()
            time.sleep(self.lock_every)

    def proc_loop(self):
        while True:
            try:
                self.procs = bench.scan_processes()
            except Exception:
                self.procs = None
            time.sleep(PROC_EVERY)

    def refresh_now(self):
        try:
            self.state = bench.collect(with_procs=False)
            self.updated = time.time()
            self.error = None
        except Exception as problem:
            self.error = str(problem)
        threading.Thread(target=self.proc_loop_once, daemon=True).start()

    def proc_loop_once(self):
        try:
            self.procs = bench.scan_processes()
        except Exception:
            pass

    # ------------------------------------------------------------------ affichage

    def set_topmost(self):
        self.root.attributes("-topmost", self.topmost.get())

    def draw(self):
        state = self.state
        if state is None:
            self.verdict.configure(text=self.error or "lecture...", fg=RED if self.error else DIM)
        else:
            self.draw_verdict(state)
            self.draw_slots(state)
            self.draw_queue(state)
            self.draw_running(state)
            age = time.time() - (self.updated or time.time())
            extra = "" if self.procs is not None else "  ·  process : pas de scan"
            self.stamp.configure(text="maj il y a %s%s  ·  double-clic : ouvrir le dossier"
                                      % (bench.ago(age), extra))
        self.root.after(500, self.draw)

    def draw_verdict(self, state):
        free = state["slots_free"]
        if free == 2:
            text, color = "LIBRE  —  les deux slots", GREEN
        elif free == 1:
            text, color = "1 SLOT LIBRE  —  un run de jeu peut demarrer,\nun build ou un run chronometre non", ORANGE
        elif state["alone"]:
            holder = next((slot["port"] for slot in state["slots"] if slot["port"]), "?")
            text, color = "PRIS ALONE  —  %s" % holder, RED
        else:
            text, color = "LES 2 SLOTS PRIS", RED
        self.verdict.configure(text=text, fg=color)
        self.dot.itemconfigure(self.dot_shape, fill=color)

    def draw_slots(self, state):
        rows = []
        for slot in state["slots"]:
            if slot["state"] == "free":
                rows.append(("slot %d   libre" % slot["slot"], GREEN, 0, True, None))
                continue
            stale = slot["state"] == "stale"
            color = ORANGE if stale else FG
            rows.append(("slot %d   %s   %s" % (slot["slot"], "PERIME" if stale else "PRIS",
                                                bench.who(slot["port"], slot["project"])),
                         color, 0, True, slot["project"]))
            when = []
            if slot["until"]:
                when.append("jusqu'a %s" % slot["until"])
            if slot["seconds_left"] is not None:
                when.append("%s restantes" % bench.ago(slot["seconds_left"]))
            elif slot["overdue_seconds"] is not None:
                when.append("depasse de %s" % bench.ago(slot["overdue_seconds"]))
            if slot["written_at"]:
                when.append("pris a %s" % bench.clock(slot["written_at"]))
            if when:
                rows.append((" · ".join(when), DIM, 1, False, None))
            if stale:
                rows.append(("reprenable par le prochain en file", ORANGE, 1, False, None))
            rows.append(("why : %s" % (slot["why"] or "(pas de raison donnee)"), BLUE, 1, False, None))
        if state["alone"]:
            rows.append(("les deux slots au meme port : il tient le bench alone", DIM, 0, False, None))
        self.slots.rows(rows)

    def draw_queue(self, state):
        queue = state["queue"]
        self.queue.set_title("FILE D'ATTENTE  (%d)" % len(queue))
        rows = []
        if not queue:
            rows.append(("personne n'attend", GREEN, 0, False, None))
        for waiter in queue:
            line = "%d. %s · attend %s" % (waiter["position"],
                                           bench.who(waiter["port"], waiter["project"]),
                                           bench.ago(waiter["waiting_seconds"]))
            if waiter["refresh_age_seconds"] is not None:
                line += " · refresh %s" % bench.ago(waiter["refresh_age_seconds"])
            rows.append((line, FG, 0, False, waiter["project"]))
            if waiter["dead"]:
                rows.append(("shell mort : entree jetee au prochain tour", ORANGE, 1, False, None))
            ask = waiter["ask"]
            if ask:
                rows.append(("demande a passer : ~%s min — %s" % (ask["minutes"] or "?",
                                                                  ask["why"] or "(sans raison)"),
                             BLUE, 1, False, None))
                if ask["lapses_in_seconds"] is not None:
                    rows.append(("perime dans %s · seuls les ports devant peuvent la laisser passer"
                                 % bench.ago(ask["lapses_in_seconds"]), DIM, 1, False, None))
        loose = [ask for ask in state["asks"]
                 if ask["port"] not in {waiter["port"] for waiter in queue}]
        for ask in loose:
            rows.append(("%s demande a passer sans etre en file : ~%s min — %s%s"
                         % (ask["port"], ask["minutes"] or "?", ask["why"] or "(sans raison)",
                            " [perimee]" if ask["lapsed"] else ""), DIM, 0, False, None))
        self.queue.rows(rows)

    def draw_running(self, state):
        procs = self.procs
        rows = []
        if procs is None:
            self.running.set_title("CE QUI TOURNE")
            rows.append(("scan des process indisponible", DIM, 0, False, None))
            self.running.rows(rows)
            return
        runners = [proc for proc in procs if proc["kind"] == "runner"]
        self.running.set_title("CE QUI TOURNE  (%d runner%s)"
                               % (len(runners), "" if len(runners) == 1 else "s"))
        for proc in runners:
            rows.append(("%s · %s · pid %s · depuis %s"
                         % (proc["name"], bench.label(proc["project"]), proc["pid"],
                            (proc["started"] or "?")[11:16]), GREEN, 0, False, proc["project"]))
        if not runners:
            rows.append(("aucun jeu ne tourne", DIM, 0, False, None))
        for kind in ("build", "shell"):
            group = {}
            for proc in procs:
                if proc["kind"] == kind:
                    group.setdefault(bench.label(proc["project"]), 0)
                    group[bench.label(proc["project"])] += 1
            for project in sorted(group):
                rows.append(("%-6s %s : %d process" % (kind, project, group[project]),
                             DIM, 0, False, project if project.startswith("D:") else None))
        self.running.rows(rows)


def main(argv):
    lock_every = LOCK_EVERY
    if len(argv) > 1:
        try:
            lock_every = max(0.5, float(argv[1]))
        except ValueError:
            pass
    root = tk.Tk()
    Window(root, lock_every)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
