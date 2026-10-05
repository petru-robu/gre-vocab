"""GRE Vocabulary Trainer - Tkinter front end.  Run:  python vocab_app.py"""

import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from vocab_core import (
    KNOWN_STREAK, LEGACY_STATS_FILE, PROGRESS_FILE, Deck, Progress, Session,
    learn_queue, practice_pool, practice_queue,
)

C = {
    "bg": "#f3f4f9", "card": "#ffffff", "border": "#e0e3ee",
    "text": "#1d2136", "muted": "#6a7088", "accent": "#4f46e5", "accent_hover": "#4338ca",
    "yes": "#16a34a", "yes_hover": "#15803d", "no": "#dc2626", "no_hover": "#b91c1c",
    "soft": "#e8eaf6", "soft_hover": "#d9dcef", "disabled": "#eceef5", "disabled_text": "#a3a8bd",
    "known": "#22c55e", "learning": "#f59e0b", "new": "#cfd3e3",
    "note_bg": "#fff6df", "note_fg": "#7a5200",
}
BUTTONS = {  # kind -> (background, text, hover)
    "primary": (C["accent"], "#ffffff", C["accent_hover"]),
    "secondary": (C["soft"], C["text"], C["soft_hover"]),
    "yes": (C["yes"], "#ffffff", C["yes_hover"]),
    "no": (C["no"], "#ffffff", C["no_hover"]),
}
LEVEL_RAMP = ((0x0E, 0xA5, 0xE9), (0x63, 0x66, 0xF1), (0xC0, 0x26, 0xD3))  # sky -> indigo -> fuchsia
POS_NAMES = {"adj.": "adjective", "n.": "noun", "v.": "verb"}
IDLE_LIMIT = 60  # seconds without input before the study timer pauses
PRACTICE_COUNTS = ["5", "10", "15", "20", "25", "50", "100", "All"]
FAMILY = "TkDefaultFont"


def font(size, weight="normal", slant="roman"):
    return (FAMILY, size, f"{weight} {slant}".replace(" roman", "").strip())


def pick_family(root):
    available = set(tkfont.families(root))
    for name in ("Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Cantarell", "Noto Sans", "DejaVu Sans", "Arial"):
        if name in available:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


def level_color(level, levels=10):
    t = (level - 1) / max(levels - 1, 1) * (len(LEVEL_RAMP) - 1)
    i = min(int(t), len(LEVEL_RAMP) - 2)
    a, b = LEVEL_RAMP[i], LEVEL_RAMP[i + 1]
    return "#%02x%02x%02x" % tuple(round(a[k] + (b[k] - a[k]) * (t - i)) for k in range(3))


def pos_text(pos):
    """'v./n.' -> 'verb / noun'"""
    return " / ".join(POS_NAMES.get(p.strip(), p.strip()) for p in pos.split("/"))


def clock(seconds):
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# ------------------------------------------------------------------------ widgets

class Btn(tk.Button):
    def __init__(self, parent, text, command, kind="secondary", **kw):
        self.kind = kind
        bg, fg, hover = BUTTONS[kind]
        opts = dict(padx=16, pady=8, font=font(11, "bold"))
        opts.update(kw)
        super().__init__(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                         activeforeground=fg, disabledforeground=C["disabled_text"], relief="flat", bd=0,
                         cursor="hand2", takefocus=0, **opts)
        self.bind("<Enter>", lambda e: self["state"] == "normal" and self.config(bg=hover))
        self.bind("<Leave>", lambda e: self["state"] == "normal" and self.config(bg=bg))

    def enable(self, flag=True):
        bg = BUTTONS[self.kind][0]
        self.config(state="normal" if flag else "disabled", bg=bg if flag else C["disabled"],
                    cursor="hand2" if flag else "arrow")


class StackedBar(tk.Canvas):
    """known / learning / new, drawn as one proportional bar."""

    def __init__(self, parent, height=8, bg=C["card"]):
        super().__init__(parent, height=height, bd=0, highlightthickness=0, bg=bg)
        self.parts = (0, 0, 1)
        self.bind("<Configure>", lambda e: self.redraw())

    def set(self, known, learning, new):
        self.parts = (known, learning, new)
        self.redraw()

    def redraw(self):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        total = sum(self.parts) or 1
        x = 0
        for n, color in zip(self.parts, (C["known"], C["learning"], C["new"])):
            if n:
                nx = x + width * n / total
                self.create_rectangle(x, 0, nx, height, fill=color, width=0)
                x = nx


class LevelBadge(tk.Canvas):
    def __init__(self, parent, level, size=34, bg=C["card"]):
        super().__init__(parent, width=size, height=size, bd=0, highlightthickness=0, bg=bg)
        self.create_oval(1, 1, size - 1, size - 1, fill=level_color(level), width=0)
        self.create_text(size / 2, size / 2, text=str(level), fill="#ffffff", font=font(12, "bold"))


class Legend(tk.Frame):
    def __init__(self, parent, counts, bg, size=10):
        super().__init__(parent, bg=bg)
        for key, label in (("known", "known"), ("learning", "learning"), ("new", "new")):
            tk.Label(self, text="●", fg=C[key], bg=bg, font=font(size)).pack(side="left")
            tk.Label(self, text=f"{counts[key]} {label}", fg=C["muted"], bg=bg,
                     font=font(size)).pack(side="left", padx=(2, 12))


class Screen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.container, bg=C["bg"])
        self.app = app

    def on_close(self):
        pass


# ------------------------------------------------------------------------ home

class BatchCard(tk.Frame):
    def __init__(self, parent, app, batch):
        super().__init__(parent, bg=C["card"], highlightthickness=1, highlightbackground=C["border"],
                         padx=16, pady=14)
        counts = app.progress.counts(batch.words)

        top = tk.Frame(self, bg=C["card"])
        top.pack(fill="x")
        LevelBadge(top, batch.number).pack(side="left")
        tk.Label(top, text=batch.title, font=font(13, "bold"), bg=C["card"], fg=C["text"]).pack(side="left", padx=(10, 6))
        tk.Label(top, text=batch.label, font=font(11), bg=C["card"], fg=C["muted"]).pack(side="left")
        link = tk.Label(top, text="view words", font=font(10), bg=C["card"], fg=C["accent"], cursor="hand2")
        link.pack(side="right")
        link.bind("<Button-1>", lambda e: app.show_stats(level=batch.number))

        preview = "  ·  ".join(batch.words[:4]) + "  …"
        tk.Label(self, text=preview, font=font(10, slant="italic"), bg=C["card"], fg=C["muted"],
                 anchor="w").pack(fill="x", pady=(8, 8))

        bar = StackedBar(self)
        bar.pack(fill="x")
        bar.set(**counts)

        bottom = tk.Frame(self, bg=C["card"])
        bottom.pack(fill="x", pady=(10, 0))
        Legend(bottom, counts, C["card"]).pack(side="left")
        Btn(bottom, "Practice…", lambda: app.open_practice([batch.number]), "secondary",
            padx=12, pady=5, font=font(10, "bold")).pack(side="right")
        Btn(bottom, "Learn", lambda: app.start_learn(batch.number), "primary",
            padx=14, pady=5, font=font(10, "bold")).pack(side="right", padx=(0, 8))


class HomeScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        deck, progress = app.deck, app.progress
        all_words = list(deck.words)
        counts = progress.counts(all_words)

        header = tk.Frame(self, bg=C["bg"])
        header.pack(fill="x", padx=28, pady=(22, 6))
        left = tk.Frame(header, bg=C["bg"])
        left.pack(side="left")
        tk.Label(left, text="GRE Vocabulary Trainer", font=font(22, "bold"), bg=C["bg"], fg=C["text"]).pack(anchor="w")
        tk.Label(left, text=f"{len(all_words)} core words in {len(deck.batches)} levels, easiest to hardest "
                            f"· chosen from {deck.lists_total} GRE high-frequency word lists",
                 font=font(10), bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(2, 0))

        answers, seconds = progress.today()
        streak = progress.day_streak()
        today = f"Today: {answers} answers · {seconds // 60} min"
        if streak:
            today += f"   ·   {streak}-day streak"
        tk.Label(header, text=today, font=font(10), bg=C["bg"], fg=C["muted"]).pack(side="right", anchor="s")

        overall = tk.Frame(self, bg=C["bg"])
        overall.pack(fill="x", padx=28, pady=(8, 12))
        bar = StackedBar(overall, height=10, bg=C["bg"])
        bar.pack(fill="x")
        bar.set(**counts)
        legend_row = tk.Frame(overall, bg=C["bg"])
        legend_row.pack(fill="x", pady=(6, 0))
        Legend(legend_row, counts, C["bg"]).pack(side="left")
        tk.Label(legend_row, text=f"A word counts as known after {KNOWN_STREAK} correct answers in a row",
                 font=font(9), bg=C["bg"], fg=C["muted"]).pack(side="right")

        footer = tk.Frame(self, bg=C["bg"])
        footer.pack(side="bottom", fill="x", padx=28, pady=(8, 18))
        Btn(footer, "Mixed practice…", lambda: app.open_practice(range(1, len(deck.batches) + 1)),
            "primary").pack(side="left")
        Btn(footer, "Statistics & word list", app.show_stats, "secondary").pack(side="left", padx=10)
        self.repeat_var = tk.BooleanVar(value=progress.settings.get("repeat_missed", True))
        tk.Checkbutton(footer, text="Repeat missed cards during a session", variable=self.repeat_var,
                       command=self.save_repeat, bg=C["bg"], activebackground=C["bg"], fg=C["text"],
                       selectcolor=C["card"], font=font(10), takefocus=0, highlightthickness=0).pack(side="right")

        # scrollable grid of level cards
        area = tk.Frame(self, bg=C["bg"])
        area.pack(fill="both", expand=True, padx=(28, 12))
        self.canvas = tk.Canvas(area, bg=C["bg"], highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        grid = tk.Frame(self.canvas, bg=C["bg"])
        window = self.canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(window, width=e.width))
        grid.columnconfigure(0, weight=1, uniform="cards")
        grid.columnconfigure(1, weight=1, uniform="cards")
        for i, batch in enumerate(deck.batches):
            BatchCard(grid, app, batch).grid(row=i // 2, column=i % 2, sticky="nsew",
                                             padx=(0, 16 if i % 2 == 0 else 4), pady=(0, 14))

        for seq, delta in (("<Button-4>", -1), ("<Button-5>", 1)):
            app.root.bind(seq, lambda e, d=delta: self.canvas.yview_scroll(d * 2, "units"))
        app.root.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll((-2 if e.delta > 0 else 2), "units"))

    def save_repeat(self):
        self.app.progress.settings["repeat_missed"] = self.repeat_var.get()
        self.app.progress.save()

    def on_close(self):
        for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.app.root.unbind(seq)


# ------------------------------------------------------------------------ study

class StudyScreen(Screen):
    def __init__(self, app, session):
        super().__init__(app)
        self.session = session
        self.revealed = False
        self.active_seconds = 0
        self.last_input = time.monotonic()
        self.closed = False
        self.after_id = None

        top = tk.Frame(self, bg=C["bg"])
        top.pack(fill="x", padx=28, pady=(18, 4))
        Btn(top, "← Levels", self.end, "secondary", padx=12, pady=5, font=font(10, "bold")).pack(side="left")
        if session.level:
            LevelBadge(top, session.level, size=28, bg=C["bg"]).pack(side="left", padx=(14, 6))
        tk.Label(top, text=session.title, font=font(14, "bold"), bg=C["bg"], fg=C["text"]).pack(
            side="left", padx=(0 if session.level else 14, 0))
        self.timer_label = tk.Label(top, text="00:00", font=font(11, "bold"), bg=C["bg"], fg=C["muted"])
        self.timer_label.pack(side="right")

        prog = tk.Frame(self, bg=C["bg"])
        prog.pack(fill="x", padx=28, pady=(8, 10))
        self.progress_bar = ttk.Progressbar(prog, maximum=max(session.total, 1), style="Study.Horizontal.TProgressbar")
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_label = tk.Label(prog, text="", font=font(10), bg=C["bg"], fg=C["muted"], width=24, anchor="e")
        self.progress_label.pack(side="right", padx=(12, 0))

        self.card = tk.Frame(self, bg=C["card"], highlightthickness=1, highlightbackground=C["border"])
        self.card.pack(fill="both", expand=True, padx=28)
        self.retry_label = tk.Label(self.card, text="", font=font(10, "bold"), bg=C["card"], fg=C["learning"])
        self.retry_label.pack(pady=(44, 0))
        self.word_label = tk.Label(self.card, text="", font=font(54, "bold"), bg=C["card"], fg=C["text"])
        self.word_label.pack(pady=(4, 8))
        self.hint_label = tk.Label(self.card, text="Do you know this word?  Recall the meaning, then reveal the answer.",
                                   font=font(13), bg=C["card"], fg=C["muted"])
        self.hint_label.pack(pady=(12, 0))

        self.answer_box = tk.Frame(self.card, bg=C["card"])
        self.pos_label = tk.Label(self.answer_box, font=font(12, slant="italic"), bg=C["card"], fg=C["muted"])
        self.pos_label.pack()
        self.def_label = tk.Label(self.answer_box, font=font(20), bg=C["card"], fg=C["text"], justify="center")
        self.def_label.pack(pady=(6, 10))
        self.syn_label = tk.Label(self.answer_box, font=font(13, "bold"), bg=C["card"], fg=C["accent"], justify="center")
        self.syn_label.pack()
        self.ex_label = tk.Label(self.answer_box, font=font(13, slant="italic"), bg=C["card"], fg=C["text"], justify="center")
        self.ex_label.pack(pady=(10, 0))
        self.note_box = tk.Frame(self.answer_box, bg=C["note_bg"])
        self.note_label = tk.Label(self.note_box, font=font(11), bg=C["note_bg"], fg=C["note_fg"], justify="left")
        self.note_label.pack(padx=12, pady=6)
        self.lists_label = tk.Label(self.answer_box, font=font(10), bg=C["card"], fg=C["muted"])
        self.lists_label.pack(pady=(12, 0))
        self.wrapped = (self.def_label, self.syn_label, self.ex_label, self.note_label)
        self.card.bind("<Configure>", lambda e: self.rewrap(e.width))

        actions = tk.Frame(self, bg=C["bg"], height=64)
        actions.pack(fill="x", padx=28, pady=(14, 4))
        actions.pack_propagate(False)
        self.reveal_btn = Btn(actions, "Show answer    [Space]", self.reveal, "primary", pady=12, padx=30)
        self.reveal_btn.pack(expand=True)
        self.answer_row = tk.Frame(actions, bg=C["bg"])
        Btn(self.answer_row, "No, didn't know    [N]", lambda: self.answer(False), "no", pady=12, padx=26).pack(side="left", padx=8)
        Btn(self.answer_row, "Yes, I knew it    [Y]", lambda: self.answer(True), "yes", pady=12, padx=26).pack(side="left", padx=8)

        bottom = tk.Frame(self, bg=C["bg"])
        bottom.pack(fill="x", padx=28, pady=(0, 14))
        self.undo_btn = Btn(bottom, "Undo last answer    [U]", self.undo, "secondary", padx=12, pady=5, font=font(10, "bold"))
        self.undo_btn.pack(side="left")
        self.score_label = tk.Label(bottom, text="", font=font(10), bg=C["bg"], fg=C["muted"])
        self.score_label.pack(side="right")

        for seq, fn in (("<space>", self.reveal), ("<Return>", self.reveal),
                        ("y", lambda: self.answer(True)), ("Y", lambda: self.answer(True)), ("<Right>", lambda: self.answer(True)),
                        ("n", lambda: self.answer(False)), ("N", lambda: self.answer(False)), ("<Left>", lambda: self.answer(False)),
                        ("u", self.undo), ("U", self.undo), ("<BackSpace>", self.undo), ("<Escape>", self.end)):
            app.root.bind(seq, lambda e, fn=fn: fn())
        self.bound = ("<space>", "<Return>", "y", "Y", "<Right>", "n", "N", "<Left>", "u", "U", "<BackSpace>", "<Escape>")

        self.show_card()
        self.tick()

    def rewrap(self, width):
        for label in self.wrapped:
            label.config(wraplength=max(width - 120, 200))

    def tick(self):
        if time.monotonic() - self.last_input < IDLE_LIMIT:
            self.active_seconds += 1
        self.timer_label.config(text=clock(self.active_seconds))
        self.after_id = self.after(1000, self.tick)

    def touch(self):
        self.last_input = time.monotonic()

    def show_card(self):
        s = self.session
        word = s.deck.words[s.current]
        self.revealed = False
        self.word_label.config(text=word.text)
        self.retry_label.config(text="RETRY · you missed this one earlier" if s.is_retry else "")
        self.answer_box.pack_forget()
        self.hint_label.pack(pady=(12, 0))
        self.answer_row.pack_forget()
        self.reveal_btn.pack(expand=True)
        self.progress_bar["value"] = len(s.cleared)
        self.progress_label.config(text=f"{len(s.cleared)} / {s.total} done")
        self.score_label.config(text=f"Knew {s.known_count}  ·  Missed {s.missed_count}")
        self.undo_btn.enable(s.can_undo)

    def reveal(self):
        if self.revealed or self.closed:
            return
        self.touch()
        word = self.session.deck.words[self.session.current]
        self.revealed = True
        self.hint_label.pack_forget()
        self.pos_label.config(text=pos_text(word.pos))
        self.def_label.config(text=word.definition)
        self.syn_label.config(text="Synonyms:  " + ", ".join(word.synonyms))
        self.ex_label.config(text=f"“{word.example}”")
        if word.note:
            self.note_label.config(text="Note: " + word.note)
            self.note_box.pack(pady=(12, 0), before=self.lists_label)
        else:
            self.note_box.pack_forget()
        self.lists_label.config(text=f"Found on {word.lists} of {self.session.deck.lists_total} GRE high-frequency word lists")
        self.answer_box.pack(fill="x", padx=30, pady=(4, 10))
        self.reveal_btn.pack_forget()
        self.answer_row.pack(expand=True)
        self.rewrap(self.card.winfo_width())

    def answer(self, correct):
        if not self.revealed or self.closed:
            return
        self.touch()
        self.session.answer(correct)
        self.app.warn_if_unsaved()
        if self.session.is_done:
            self.app.finish_session(self.session)
        else:
            self.show_card()

    def undo(self):
        if self.closed or not self.session.undo():
            return
        self.touch()
        self.show_card()
        self.reveal()

    def end(self):
        if self.closed:
            return
        if self.session.first_try:
            self.app.finish_session(self.session)
        else:
            self.app.show_home()

    def on_close(self):
        if self.closed:
            return
        self.closed = True
        if self.after_id:
            self.after_cancel(self.after_id)
        for seq in self.bound:
            self.app.root.unbind(seq)
        self.app.progress.add_study_time(self.active_seconds)


# ---------------------------------------------------------------------- summary

class SummaryScreen(Screen):
    def __init__(self, app, session, finished):
        super().__init__(app)
        deck = app.deck
        known, missed = session.known_count, session.missed_count

        tk.Label(self, text="Session complete" if finished else "Session ended", font=font(22, "bold"),
                 bg=C["bg"], fg=C["text"]).pack(pady=(28, 2))
        tk.Label(self, text=session.title, font=font(12), bg=C["bg"], fg=C["muted"]).pack()

        tiles = tk.Frame(self, bg=C["bg"])
        tiles.pack(pady=18)
        for value, label, color in ((str(known), "knew it", C["yes"]), (str(missed), "missed", C["no"]),
                                    (f"{session.accuracy * 100:.0f}%", "first-try accuracy", C["accent"])):
            tile = tk.Frame(tiles, bg=C["card"], highlightthickness=1, highlightbackground=C["border"], padx=26, pady=12)
            tile.pack(side="left", padx=8)
            tk.Label(tile, text=value, font=font(26, "bold"), bg=C["card"], fg=color).pack()
            tk.Label(tile, text=label, font=font(10), bg=C["card"], fg=C["muted"]).pack()

        if session.level:
            counts = app.progress.counts(deck.batch(session.level).words)
            bar = StackedBar(self, height=8, bg=C["bg"])
            bar.pack(fill="x", padx=120)
            bar.set(**counts)
            row = tk.Frame(self, bg=C["bg"])
            row.pack(pady=(6, 0))
            tk.Label(row, text=f"Level {session.level} now:", font=font(10), bg=C["bg"], fg=C["muted"]).pack(side="left", padx=(0, 8))
            Legend(row, counts, C["bg"]).pack(side="left")

        missed_words = session.missed_words
        if missed_words:
            tk.Label(self, text="Words to review", font=font(12, "bold"), bg=C["bg"], fg=C["text"]).pack(pady=(16, 4))
            box = tk.Frame(self, bg=C["card"], highlightthickness=1, highlightbackground=C["border"])
            box.pack(fill="both", expand=True, padx=60)
            text = tk.Text(box, wrap="word", font=font(11), bg=C["card"], fg=C["text"], relief="flat",
                           padx=14, pady=10, height=8, cursor="arrow")
            scroll = ttk.Scrollbar(box, command=text.yview)
            text.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            text.pack(side="left", fill="both", expand=True)
            text.tag_configure("word", font=font(11, "bold"), foreground=C["accent"])
            text.tag_configure("pos", font=font(10, slant="italic"), foreground=C["muted"])
            for w in missed_words:
                word = deck.words[w]
                text.insert("end", word.text, "word")
                text.insert("end", f"  {word.pos}  ", "pos")
                text.insert("end", f"{word.definition}\n")
            text.config(state="disabled")
        else:
            tk.Label(self, text="No misses — nicely done.", font=font(12), bg=C["bg"], fg=C["muted"]).pack(pady=24, expand=True)

        buttons = tk.Frame(self, bg=C["bg"])
        buttons.pack(pady=18)
        if missed_words:
            Btn(buttons, f"Practice the {len(missed_words)} missed", lambda: app.start_session(
                missed_words, f"Missed words · {session.title}", "practice", session.level), "primary").pack(side="left", padx=6)
        if session.can_undo and finished:
            Btn(buttons, "Undo last answer", lambda: app.resume(session), "secondary").pack(side="left", padx=6)
        Btn(buttons, "Back to levels", app.show_home, "primary" if not missed_words else "secondary").pack(side="left", padx=6)


# ---------------------------------------------------------------------- dialogs

class PracticeDialog(tk.Toplevel):
    def __init__(self, app, preselected):
        super().__init__(app.root, bg=C["bg"], padx=22, pady=18)
        self.app = app
        self.title("Practice")
        self.transient(app.root)
        self.resizable(False, False)
        deck, progress = app.deck, app.progress
        preselected = set(preselected)

        tk.Label(self, text="Practice", font=font(16, "bold"), bg=C["bg"], fg=C["text"]).grid(row=0, column=0, columnspan=5, sticky="w")
        tk.Label(self, text="From which levels?", font=font(10), bg=C["bg"], fg=C["muted"]).grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 4))
        self.levels = {}
        for i, batch in enumerate(deck.batches):
            var = tk.BooleanVar(value=batch.number in preselected)
            var.trace_add("write", lambda *a: self.update_info())
            self.levels[batch.number] = var
            tk.Checkbutton(self, text=f"Level {batch.number}", variable=var, bg=C["bg"], activebackground=C["bg"],
                           selectcolor=C["card"], font=font(10), takefocus=0, fg=C["text"],
                           highlightthickness=0).grid(
                row=2 + i // 5, column=i % 5, sticky="w", padx=(0, 10))
        quick = tk.Frame(self, bg=C["bg"])
        quick.grid(row=4, column=0, columnspan=5, sticky="w", pady=(2, 8))
        Btn(quick, "All", lambda: self.set_all(True), "secondary", padx=10, pady=2, font=font(9, "bold")).pack(side="left", padx=(0, 6))
        Btn(quick, "None", lambda: self.set_all(False), "secondary", padx=10, pady=2, font=font(9, "bold")).pack(side="left")

        studied_in_selection = any(progress.get(w).attempts for w in practice_pool(deck, preselected))
        saved = progress.settings.get("practice_method")
        self.method = tk.StringVar(value=saved if saved in ("weak", "random") and studied_in_selection else
                                   ("weak" if studied_in_selection else "random"))
        self.method.trace_add("write", lambda *a: self.update_info())
        tk.Label(self, text="Which words?", font=font(10), bg=C["bg"], fg=C["muted"]).grid(row=5, column=0, columnspan=5, sticky="w", pady=(6, 2))
        for r, (value, text) in enumerate((("weak", "Weakest words — the ones I know least"),
                                           ("random", "Random sample"))):
            tk.Radiobutton(self, text=text, value=value, variable=self.method, bg=C["bg"], activebackground=C["bg"],
                           selectcolor=C["card"], font=font(11), takefocus=0, fg=C["text"],
                           highlightthickness=0).grid(
                row=6 + r, column=0, columnspan=5, sticky="w")

        count_row = tk.Frame(self, bg=C["bg"])
        count_row.grid(row=8, column=0, columnspan=5, sticky="w", pady=(10, 0))
        tk.Label(count_row, text="How many?", font=font(10), bg=C["bg"], fg=C["muted"]).pack(side="left", padx=(0, 8))
        self.count = tk.StringVar(value=str(progress.settings.get("practice_count", "10")))
        if self.count.get() not in PRACTICE_COUNTS:
            self.count.set("10")
        box = ttk.Combobox(count_row, textvariable=self.count, values=PRACTICE_COUNTS, width=6, state="readonly")
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda e: self.update_info())

        self.info = tk.Label(self, text="", font=font(10), bg=C["bg"], fg=C["text"], justify="left", wraplength=420)
        self.info.grid(row=9, column=0, columnspan=5, sticky="w", pady=(12, 12))

        buttons = tk.Frame(self, bg=C["bg"])
        buttons.grid(row=10, column=0, columnspan=5, sticky="e")
        Btn(buttons, "Cancel", self.destroy, "secondary").pack(side="left", padx=(0, 8))
        self.start_btn = Btn(buttons, "Start practice", self.start, "primary")
        self.start_btn.pack(side="left")

        self.bind("<Escape>", lambda e: self.destroy())
        self.update_info()
        self.update_idletasks()
        x = app.root.winfo_rootx() + (app.root.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.root.winfo_rooty() + max((app.root.winfo_height() - self.winfo_reqheight()) // 3, 20)
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.after(50, self.grab)

    def grab(self):
        try:
            self.grab_set()  # modal once the window is on screen
        except tk.TclError:
            pass

    def set_all(self, flag):
        for var in self.levels.values():
            var.set(flag)

    def selected(self):
        return [n for n, v in self.levels.items() if v.get()]

    def limit(self):
        return None if self.count.get() == "All" else int(self.count.get())

    def update_info(self):
        deck, progress = self.app.deck, self.app.progress
        levels = self.selected()
        pool = practice_pool(deck, levels)
        studied = sum(1 for w in pool if progress.get(w).attempts)
        limit = self.limit()
        ok = True
        if not levels:
            msg, ok = "Pick at least one level.", False
        elif self.method.get() == "weak":
            if not studied:
                msg, ok = ("You haven't answered any of these words yet. Use Learn on the level first, "
                           "or switch to Random sample."), False
            else:
                msg = (f"{min(limit or studied, studied)} weakest of the {studied} words you've already answered "
                       f"({len(pool)} words in the selected levels).")
        else:
            msg = f"{min(limit or len(pool), len(pool))} random words out of {len(pool)} in the selected levels."
        self.info.config(text=msg, fg=C["text"] if ok else C["no"])
        self.start_btn.enable(ok)

    def start(self):
        levels, method, limit = self.selected(), self.method.get(), self.limit()
        queue = practice_queue(self.app.deck, self.app.progress, levels, method, limit)
        if not queue:
            return
        settings = self.app.progress.settings
        settings["practice_method"], settings["practice_count"] = method, self.count.get()
        self.app.progress.save()
        if len(levels) == len(self.app.deck.batches):
            where = "all levels"
        elif len(levels) == 1:
            where = f"Level {levels[0]}"
        else:
            where = "Levels " + ", ".join(map(str, levels))
        what = "weakest" if method == "weak" else "random"
        self.destroy()
        self.app.start_session(queue, f"Practice · {where} · {len(queue)} {what}", "practice",
                               levels[0] if len(levels) == 1 else None)


class StatsWindow(tk.Toplevel):
    COLUMNS = (("word", "Word", 140, "w"), ("level", "Level", 60, "center"), ("status", "Status", 80, "center"),
               ("correct", "Knew", 55, "center"), ("wrong", "Missed", 60, "center"),
               ("recent", "Last answers", 110, "center"), ("seen", "Last seen", 100, "center"))

    def __init__(self, app, level=None):
        super().__init__(app.root, bg=C["bg"])
        self.app = app
        self.title("Statistics & word list")
        self.geometry("860x640")
        self.minsize(720, 520)
        self.sort_key, self.sort_reverse = "level", False

        words = list(app.deck.words)
        counts = app.progress.counts(words)
        answered = sum(app.progress.get(w).attempts for w in words)
        right = sum(app.progress.get(w).correct for w in words)
        top = tk.Frame(self, bg=C["bg"])
        top.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(top, text=f"{counts['known']} known · {counts['learning']} learning · {counts['new']} new",
                 font=font(13, "bold"), bg=C["bg"], fg=C["text"]).pack(side="left")
        tk.Label(top, text=f"{answered} answers in total" + (f" · {right / answered * 100:.0f}% correct" if answered else ""),
                 font=font(10), bg=C["bg"], fg=C["muted"]).pack(side="right")

        filters = tk.Frame(self, bg=C["bg"])
        filters.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(filters, text="Level", font=font(10), bg=C["bg"], fg=C["muted"]).pack(side="left")
        self.level_var = tk.StringVar(value=f"Level {level}" if level else "All levels")
        level_box = ttk.Combobox(filters, textvariable=self.level_var, state="readonly", width=10,
                                 values=["All levels"] + [b.title for b in app.deck.batches])
        level_box.pack(side="left", padx=(6, 16))
        tk.Label(filters, text="Status", font=font(10), bg=C["bg"], fg=C["muted"]).pack(side="left")
        self.status_var = tk.StringVar(value="All")
        status_box = ttk.Combobox(filters, textvariable=self.status_var, state="readonly", width=10,
                                  values=["All", "Learning", "New", "Known"])
        status_box.pack(side="left", padx=6)
        for box in (level_box, status_box):
            box.bind("<<ComboboxSelected>>", lambda e: self.fill())

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=16)
        self.tree = ttk.Treeview(body, columns=[c[0] for c in self.COLUMNS], show="headings", selectmode="browse")
        for key, title, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=title, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=key == "word")
        scroll = ttk.Scrollbar(body, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("known", background="#e6f6ec")
        self.tree.tag_configure("learning", background="#fff3d6")
        self.tree.tag_configure("new", background="#ffffff")
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)

        self.detail = tk.Frame(self, bg=C["card"], highlightthickness=1, highlightbackground=C["border"])
        self.detail.pack(fill="x", padx=16, pady=12)
        self.detail_title = tk.Label(self.detail, text="Select a word to see its details", font=font(13, "bold"),
                                     bg=C["card"], fg=C["text"], anchor="w")
        self.detail_title.pack(fill="x", padx=14, pady=(10, 0))
        self.detail_body = tk.Label(self.detail, text="", font=font(11), bg=C["card"], fg=C["text"], anchor="w",
                                    justify="left", wraplength=800)
        self.detail_body.pack(fill="x", padx=14, pady=(2, 10))
        self.detail.bind("<Configure>", lambda e: self.detail_body.config(wraplength=max(e.width - 40, 200)))
        self.fill()

    def rows(self):
        deck, progress = self.app.deck, self.app.progress
        level = None if self.level_var.get() == "All levels" else int(self.level_var.get().split()[1])
        status = self.status_var.get().lower()
        for batch in deck.batches:
            if level and batch.number != level:
                continue
            for text in batch.words:
                p = progress.get(text)
                if status != "all" and p.status != status:
                    continue
                yield text, batch.number, p

    def fill(self):
        keys = {
            "word": lambda r: r[0], "level": lambda r: (r[1], self.app.deck.batch(r[1]).words.index(r[0])),
            "status": lambda r: ("new", "learning", "known").index(r[2].status),
            "correct": lambda r: r[2].correct, "wrong": lambda r: r[2].wrong,
            "recent": lambda r: r[2].weakness, "seen": lambda r: r[2].last_seen,
        }
        rows = sorted(self.rows(), key=keys[self.sort_key], reverse=self.sort_reverse)
        self.tree.delete(*self.tree.get_children())
        for text, level, p in rows:
            recent = " ".join("✓" if ch == "1" else "✗" for ch in p.history[-6:]) or "—"
            seen = p.last_seen[:10] or "—"
            self.tree.insert("", "end", iid=text, tags=(p.status,),
                             values=(text, level, p.status.capitalize(), p.correct, p.wrong, recent, seen))
        arrows = {k: (" ▲" if not self.sort_reverse else " ▼") if k == self.sort_key else "" for k, *_ in self.COLUMNS}
        for key, title, *_ in self.COLUMNS:
            self.tree.heading(key, text=title + arrows[key])

    def sort_by(self, key):
        self.sort_reverse = not self.sort_reverse if key == self.sort_key else (key in ("correct", "wrong", "seen"))
        self.sort_key = key
        self.fill()

    def show_detail(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        word = self.app.deck.words[selected[0]]
        self.detail_title.config(text=f"{word.text}   ({pos_text(word.pos)})")
        text = f"{word.definition}\nSynonyms: {', '.join(word.synonyms)}\n“{word.example}”"
        if word.note:
            text += f"\nNote: {word.note}"
        self.detail_body.config(text=text)


# -------------------------------------------------------------------------- app

class App:
    def __init__(self, root, progress_file=PROGRESS_FILE, legacy_file=LEGACY_STATS_FILE):
        global FAMILY
        self.root = root
        FAMILY = pick_family(root)
        root.title("GRE Vocabulary Trainer")
        root.configure(bg=C["bg"])
        width = min(1000, root.winfo_screenwidth() - 80)
        height = min(780, root.winfo_screenheight() - 120)
        root.geometry(f"{width}x{height}+{max((root.winfo_screenwidth() - width) // 2, 0)}+"
                      f"{max((root.winfo_screenheight() - height) // 3, 0)}")
        root.minsize(min(880, width), min(660, height))

        self.deck = Deck.load()
        self.progress = Progress.load(progress_file, deck=self.deck, legacy_file=legacy_file)
        self.screen = None
        self.save_warned = False

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Study.Horizontal.TProgressbar", troughcolor=C["new"], background=C["accent"],
                        bordercolor=C["bg"], lightcolor=C["accent"], darkcolor=C["accent"], thickness=8)
        style.configure("Treeview", rowheight=26, font=font(10), fieldbackground=C["card"])
        style.configure("Treeview.Heading", font=font(10, "bold"))

        menubar = tk.Menu(root)
        app_menu = tk.Menu(menubar, tearoff=0)
        app_menu.add_command(label="Levels", command=self.show_home)
        app_menu.add_command(label="Statistics & word list", command=self.show_stats)
        app_menu.add_separator()
        app_menu.add_command(label="Quit", command=self.quit)
        menubar.add_cascade(label="App", menu=app_menu)
        reset_menu = tk.Menu(menubar, tearoff=0)
        for batch in self.deck.batches:
            reset_menu.add_command(label=f"Reset Level {batch.number}…", command=lambda n=batch.number: self.reset([n]))
        reset_menu.add_separator()
        reset_menu.add_command(label="Reset all progress…", command=lambda: self.reset(None))
        menubar.add_cascade(label="Progress", menu=reset_menu)
        root.config(menu=menubar)

        self.container = tk.Frame(root, bg=C["bg"])
        self.container.pack(fill="both", expand=True)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.show_home()
        if self.progress.migrated:
            messagebox.showinfo(
                "Welcome to the new trainer",
                f"Your earlier results for {self.progress.migrated} words that are also in the new deck were carried over.\n\n"
                "Your old word list and statistics are kept in the legacy/ folder.")

    def show(self, screen):
        if self.screen:
            self.screen.on_close()
            self.screen.destroy()
        self.screen = screen
        screen.pack(fill="both", expand=True)
        self.root.focus_set()

    def show_home(self):
        self.show(HomeScreen(self))

    def start_learn(self, level):
        words = learn_queue(self.deck, self.progress, level)
        self.start_session(words, f"{self.deck.batch(level).title} · Learn", "learn", level)

    def start_session(self, words, title, kind, level=None):
        session = Session(self.deck, self.progress, words, title, kind, level,
                          repeat_missed=self.progress.settings.get("repeat_missed", True))
        self.show(StudyScreen(self, session))

    def resume(self, session):
        session.undo()
        self.show(StudyScreen(self, session))

    def finish_session(self, session):
        self.show(SummaryScreen(self, session, finished=session.is_done))

    def open_practice(self, levels):
        PracticeDialog(self, levels)

    def show_stats(self, level=None):
        StatsWindow(self, level)

    def reset(self, levels):
        if levels is None:
            words, what = list(self.deck.words), "ALL progress"
        else:
            words, what = [w for n in levels for w in self.deck.batch(n).words], f"your progress on Level {levels[0]}"
        if messagebox.askyesno("Reset progress", f"Erase {what}? This cannot be undone.", icon="warning"):
            self.progress.reset(words)
            self.show_home()

    def warn_if_unsaved(self):
        if self.progress.last_error and not self.save_warned:
            self.save_warned = True
            messagebox.showwarning("Could not save", f"Your progress could not be written to disk:\n{self.progress.last_error}")

    def quit(self):
        if self.screen:
            self.screen.on_close()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
