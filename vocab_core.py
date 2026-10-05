"""Data model and study logic for the GRE vocabulary trainer (no GUI code)."""

import copy
import json
import os
import random
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DECK_FILE = BASE_DIR / "data" / "gre_core_250.json"
PROGRESS_FILE = BASE_DIR / "vocab_progress.json"
LEGACY_STATS_FILE = BASE_DIR / "legacy" / "vocab_stats.json"

KNOWN_STREAK = 3      # this many "knew it" answers in a row = a word counts as known
HISTORY_LEN = 10      # remembered answers per word
RECENCY_DECAY = 0.8   # each older answer counts 20% less when judging weakness
RETRY_GAP = (3, 5)    # a missed card comes back after this many other cards


# --------------------------------------------------------------------------- deck

@dataclass(frozen=True)
class Word:
    text: str
    pos: str
    definition: str
    synonyms: tuple
    example: str
    note: str
    batch: int
    lists: int  # on how many of the source word lists this word appears


@dataclass(frozen=True)
class Batch:
    number: int
    label: str
    words: tuple

    @property
    def title(self):
        return f"Level {self.number}"


class Deck:
    def __init__(self, data):
        meta = data["meta"]
        self.title = meta["title"]
        self.lists_total = meta["lists_total"]
        self.sources = meta["sources"]
        self.words = {
            text: Word(
                text=text,
                pos=w["pos"],
                definition=w["definition"],
                synonyms=tuple(w["synonyms"]),
                example=w["example"],
                note=w.get("note", ""),
                batch=w["batch"],
                lists=w["lists"],
            )
            for text, w in data["words"].items()
        }
        self.batches = [
            Batch(b["number"], b["label"], tuple(b["words"])) for b in data["batches"]
        ]

    @classmethod
    def load(cls, path=DECK_FILE):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def batch(self, number):
        return self.batches[number - 1]


# ------------------------------------------------------------------------ progress

@dataclass
class WordProgress:
    correct: int = 0
    wrong: int = 0
    history: str = ""    # newest last; "1" = knew it, "0" = didn't
    last_seen: str = ""  # ISO timestamp

    @property
    def attempts(self):
        return self.correct + self.wrong

    @property
    def accuracy(self):
        return self.correct / self.attempts if self.attempts else 0.0

    @property
    def streak(self):
        return len(self.history) - len(self.history.rstrip("1"))

    @property
    def status(self):
        if not self.attempts:
            return "new"
        return "known" if self.streak >= KNOWN_STREAK else "learning"

    @property
    def weakness(self):
        """0 = solid ... 1 = always missed. Recent answers count the most; the
        +0.5 / +1 terms are a prior that keeps one lucky guess from looking solid."""
        if not self.attempts:
            return 0.5
        if self.history:
            weights = [RECENCY_DECAY ** i for i in range(len(self.history))]  # newest first
            misses = sum(w for w, r in zip(weights, reversed(self.history)) if r == "0")
            total = sum(weights)
        else:  # progress imported from an older version: counts only
            misses, total = self.wrong, self.attempts
        return (misses + 0.5) / (total + 1)

    def record(self, correct, when):
        if correct:
            self.correct += 1
        else:
            self.wrong += 1
        self.history = (self.history + ("1" if correct else "0"))[-HISTORY_LEN:]
        self.last_seen = when.isoformat(timespec="seconds")


class Progress:
    """Everything the user has done, persisted to vocab_progress.json."""

    def __init__(self, path=PROGRESS_FILE):
        self.path = Path(path)
        self.words = {}
        self.settings = {"repeat_missed": True}
        self.daily = {}  # "YYYY-MM-DD" -> {"answers": n, "seconds": n}
        self.migrated = 0
        self.last_error = None

    @classmethod
    def load(cls, path=PROGRESS_FILE, deck=None, legacy_file=LEGACY_STATS_FILE):
        progress = cls(path)
        if progress.path.exists():
            try:
                data = json.loads(progress.path.read_text(encoding="utf-8"))
                progress.settings.update(data.get("settings", {}))
                progress.daily = data.get("daily", {})
                for word, v in data.get("words", {}).items():
                    progress.words[word] = WordProgress(
                        correct=int(v.get("correct", 0)),
                        wrong=int(v.get("wrong", 0)),
                        history=str(v.get("history", ""))[-HISTORY_LEN:],
                        last_seen=str(v.get("last_seen", "")),
                    )
            except (json.JSONDecodeError, OSError, ValueError, AttributeError):
                # Keep the unreadable file around instead of silently overwriting it.
                try:
                    os.replace(progress.path, progress.path.with_suffix(".corrupt"))
                except OSError:
                    pass
                progress.words, progress.daily = {}, {}
        elif deck is not None:
            progress._import_legacy(deck, Path(legacy_file))
        return progress

    def _import_legacy(self, deck, legacy_file):
        """Carry over correct/wrong counts from the old flat-list app for words
        that are also in the new deck."""
        try:
            old = json.loads(legacy_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for word, v in old.items():
            key = word.strip().lower()
            if key in deck.words and (v.get("correct", 0) or v.get("wrong", 0)):
                self.words[key] = WordProgress(
                    correct=int(v.get("correct", 0)), wrong=int(v.get("wrong", 0))
                )
        self.migrated = len(self.words)
        if self.migrated:
            self.save()

    def save(self):
        data = {
            "version": 2,
            "settings": self.settings,
            "words": {
                w: {"correct": p.correct, "wrong": p.wrong, "history": p.history, "last_seen": p.last_seen}
                for w, p in self.words.items()
            },
            "daily": self.daily,
        }
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
            self.last_error = None
        except OSError as exc:
            self.last_error = exc

    # -- reading

    def get(self, word):
        """Progress for a word (a blank, unsaved record if it was never seen)."""
        return self.words.get(word) or WordProgress()

    def counts(self, words):
        c = Counter(self.get(w).status for w in words)
        return {"known": c["known"], "learning": c["learning"], "new": c["new"]}

    def today(self, today=None):
        day = self.daily.get((today or date.today()).isoformat(), {})
        return day.get("answers", 0), day.get("seconds", 0)

    def day_streak(self, today=None):
        """Consecutive days with at least one answer (today may still be empty)."""
        d = today or date.today()
        if not self.daily.get(d.isoformat(), {}).get("answers"):
            d -= timedelta(days=1)
        n = 0
        while self.daily.get(d.isoformat(), {}).get("answers"):
            n += 1
            d -= timedelta(days=1)
        return n

    # -- writing

    def record(self, word, correct, when=None):
        when = when or datetime.now()
        self.words.setdefault(word, WordProgress()).record(correct, when)
        day = self.daily.setdefault(when.date().isoformat(), {"answers": 0, "seconds": 0})
        day["answers"] += 1
        self.save()

    def add_study_time(self, seconds, when=None):
        if seconds <= 0:
            return
        day = self.daily.setdefault((when or datetime.now()).date().isoformat(), {"answers": 0, "seconds": 0})
        day["seconds"] += int(seconds)
        self.save()

    def reset(self, words):
        for w in words:
            self.words.pop(w, None)
        self.save()

    def checkpoint(self, word, when=None):
        """Snapshot what record() would change, so an answer can be undone."""
        day_key = (when or datetime.now()).date().isoformat()
        return (word, copy.copy(self.words.get(word)), day_key, copy.copy(self.daily.get(day_key)))

    def restore(self, checkpoint):
        word, word_state, day_key, day_state = checkpoint
        if word_state is None:
            self.words.pop(word, None)
        else:
            self.words[word] = word_state
        if day_state is None:
            self.daily.pop(day_key, None)
        else:
            self.daily[day_key] = day_state
        self.save()


# ------------------------------------------------------------------ session logic

class Session:
    """One run through a queue of words.

    Only the *first* answer for each word in a session is written to the
    progress file: a correct answer thirty seconds after a miss says little
    about long-term memory. With repeat_missed on, a missed card comes back a
    few cards later until it is answered correctly, but that retry is practice
    only and does not touch the statistics.
    """

    def __init__(self, deck, progress, words, title, kind="learn", level=None,
                 repeat_missed=True, rng=None):
        self.deck = deck
        self.progress = progress
        self.title = title
        self.kind = kind
        self.level = level  # batch number when the session is about a single level
        self.repeat_missed = repeat_missed
        self.rng = rng or random
        self.queue = list(words)
        self.total = len(self.queue)
        self.first_try = {}   # word -> answered correctly on first sight this session
        self.cleared = set()  # words that are finished for this session
        self._undo = []

    @property
    def current(self):
        return self.queue[0] if self.queue else None

    @property
    def is_retry(self):
        return self.current in self.first_try

    @property
    def is_done(self):
        return not self.queue

    @property
    def known_count(self):
        return sum(self.first_try.values())

    @property
    def missed_count(self):
        return len(self.first_try) - self.known_count

    @property
    def missed_words(self):
        return [w for w, ok in self.first_try.items() if not ok]

    @property
    def accuracy(self):
        return self.known_count / len(self.first_try) if self.first_try else 0.0

    @property
    def can_undo(self):
        return bool(self._undo)

    def answer(self, correct):
        word = self.queue[0]
        self._undo.append((
            list(self.queue), dict(self.first_try), set(self.cleared), self.progress.checkpoint(word),
        ))
        self.queue.pop(0)
        if word not in self.first_try:
            self.first_try[word] = correct
            self.progress.record(word, correct)
        if correct or not self.repeat_missed:
            self.cleared.add(word)
        else:
            gap = self.rng.randint(*RETRY_GAP)
            self.queue.insert(min(gap, len(self.queue)), word)

    def undo(self):
        if not self._undo:
            return False
        self.queue, self.first_try, self.cleared, checkpoint = self._undo.pop()
        self.progress.restore(checkpoint)
        return True


def learn_queue(deck, progress, level, rng=random):
    """Every word of a level; words never seen before come first."""
    words = list(deck.batch(level).words)
    fresh = [w for w in words if not progress.get(w).attempts]
    seen = [w for w in words if progress.get(w).attempts]
    rng.shuffle(fresh)
    rng.shuffle(seen)
    return fresh + seen


def practice_pool(deck, levels):
    return [w for n in sorted(levels) for w in deck.batch(n).words]


def practice_queue(deck, progress, levels, method, count, rng=random):
    """method 'weak': the words you know least (only words you have already
    answered at least once). method 'random': a random sample. count None = all."""
    pool = practice_pool(deck, levels)
    if method == "weak":
        pool = [w for w in pool if progress.get(w).attempts]
        rng.shuffle(pool)  # random order among equally weak words
        pool.sort(key=lambda w: progress.get(w).weakness, reverse=True)
        picked = pool[:count] if count else pool
        rng.shuffle(picked)  # don't present them hardest-first
        return picked
    return rng.sample(pool, min(count, len(pool))) if count else rng.sample(pool, len(pool))
