import random
import tkinter as tk
from tkinter import messagebox, filedialog
from dataclasses import dataclass, asdict
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WORDS_FILE = BASE_DIR / "words.txt"
STATS_FILE = BASE_DIR / "vocab_stats.json"


@dataclass
class WordStats:
    correct: int = 0
    wrong: int = 0

    @property
    def attempts(self):
        return self.correct + self.wrong

    @property
    def accuracy(self):
        return self.correct / self.attempts if self.attempts else 0.0

    @property
    def problem_score(self):
        """
        Higher = more problematic.
        - Never seen words get a moderate priority.
        - Wrong answers increase priority strongly.
        - Correct answers reduce priority gradually.
        """
        if self.attempts == 0:
            return 1.0
        return (self.wrong + 1) / (self.attempts + 2)


def load_words():
    if not WORDS_FILE.exists():
        WORDS_FILE.write_text(
            "# One word per line, in the format: word = definition\n"
            "abate = to become less intense; diminish\n"
            "prolific = producing a large amount\n"
            "equivocal = ambiguous; open to more than one interpretation\n"
            "censure = strong criticism or official disapproval\n"
            "castigate = criticize or reprimand severely\n",
            encoding="utf-8",
        )

    words = {}
    for line_no, raw in enumerate(WORDS_FILE.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            print(f"Skipping line {line_no}: expected 'word = definition'")
            continue

        word, definition = line.split("=", 1)
        word = word.strip()
        definition = definition.strip()

        if word and definition:
            words[word] = definition

    return words


def load_stats():
    if not STATS_FILE.exists():
        return {}

    try:
        data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        return {
            word: WordStats(
                correct=int(values.get("correct", 0)),
                wrong=int(values.get("wrong", 0)),
            )
            for word, values in data.items()
        }
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def save_stats(stats):
    data = {
        word: {"correct": s.correct, "wrong": s.wrong}
        for word, s in stats.items()
    }
    STATS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


class VocabApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GRE Vocabulary Trainer")
        self.root.geometry("760x620")
        self.root.minsize(650, 540)

        self.words = load_words()
        self.stats = load_stats()
        self.app_started_at = time.monotonic()

        # Ensure every current word has a stats entry.
        for word in self.words:
            self.stats.setdefault(word, WordStats())

        self.mode = "random"
        self.current_word = None
        self.definition_visible = False
        self.remaining = []
        self.session_correct = 0
        self.session_wrong = 0

        self.build_ui()
        self.start_run("random")

    def build_ui(self):
        title = tk.Label(
            self.root,
            text="GRE Vocabulary Trainer",
            font=("Arial", 24, "bold"),
        )
        title.pack(pady=(20, 4))

        self.mode_label = tk.Label(
            self.root,
            text="Random mode",
            font=("Arial", 12),
        )
        self.mode_label.pack()

        self.progress_label = tk.Label(
            self.root,
            text="",
            font=("Arial", 11),
        )
        self.progress_label.pack(pady=(5, 15))

        self.timer_label = tk.Label(
            self.root,
            text="Time open: 00:00:00",
            font=("Arial", 11, "bold"),
            fg="#2f6f3d",
        )
        self.timer_label.pack(pady=(0, 10))

        card = tk.Frame(
            self.root,
            bd=2,
            relief="groove",
            padx=30,
            pady=30,
        )
        card.pack(fill="both", expand=True, padx=35, pady=10)

        self.word_label = tk.Label(
            card,
            text="",
            font=("Arial", 36, "bold"),
            wraplength=620,
        )
        self.word_label.pack(expand=True)

        self.definition_label = tk.Label(
            card,
            text="",
            font=("Arial", 17),
            wraplength=600,
            justify="center",
        )
        self.definition_label.pack(pady=10)

        controls = tk.Frame(self.root)
        controls.pack(pady=15)

        self.show_button = tk.Button(
            controls,
            text="Show Definition",
            command=self.show_definition,
            width=18,
            height=2,
        )
        self.show_button.grid(row=0, column=0, padx=6)

        self.wrong_button = tk.Button(
            controls,
            text="Wrong / Didn't Know",
            command=lambda: self.answer(False),
            width=18,
            height=2,
            state="disabled",
        )
        self.wrong_button.grid(row=0, column=1, padx=6)

        self.correct_button = tk.Button(
            controls,
            text="OK / I Knew It",
            command=lambda: self.answer(True),
            width=18,
            height=2,
            state="disabled",
        )
        self.correct_button.grid(row=0, column=2, padx=6)

        modes = tk.Frame(self.root)
        modes.pack(pady=(0, 18))

        tk.Button(
            modes,
            text="New Random Run",
            command=lambda: self.start_run("random"),
            width=18,
        ).grid(row=0, column=0, padx=5)

        tk.Button(
            modes,
            text="Problem Words Run",
            command=lambda: self.start_run("smart"),
            width=18,
        ).grid(row=0, column=1, padx=5)

        tk.Button(
            modes,
            text="View Statistics",
            command=self.show_stats,
            width=18,
        ).grid(row=0, column=2, padx=5)

        tk.Button(
            modes,
            text="Reload words.txt",
            command=self.reload_words,
            width=18,
        ).grid(row=0, column=3, padx=5)

        self.update_timer()

    def update_timer(self):
        elapsed = time.monotonic() - self.app_started_at
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.timer_label.config(text=f"Time open: {hours:02d}:{minutes:02d}:{seconds:02d}")
        self.root.after(1000, self.update_timer)

    def start_run(self, mode):
        if not self.words:
            messagebox.showerror("No words", "Add words to words.txt first.")
            return

        self.mode = mode
        self.remaining = list(self.words.keys())
        random.shuffle(self.remaining)

        self.session_correct = 0
        self.session_wrong = 0
        self.definition_visible = False

        self.mode_label.config(
            text="Problem Words mode" if mode == "smart" else "Random mode"
        )
        self.next_card()

    def choose_smart_word(self):
        # Weighted random sampling without replacement.
        # Problem words receive higher weight, while unseen words
        # remain reasonably likely to appear.
        weighted = []
        for word in self.remaining:
            score = self.stats[word].problem_score
            # Base weight + problem weight.
            weight = 0.25 + 4.0 * score
            weighted.append((word, weight))

        total = sum(weight for _, weight in weighted)
        r = random.uniform(0, total)
        cumulative = 0

        for word, weight in weighted:
            cumulative += weight
            if r <= cumulative:
                return word

        return weighted[-1][0]

    def next_card(self):
        if not self.remaining:
            self.finish_run()
            return

        if self.mode == "smart":
            word = self.choose_smart_word()
            self.remaining.remove(word)
        else:
            word = self.remaining.pop()

        self.current_word = word
        self.definition_visible = False

        self.word_label.config(text=word)
        self.definition_label.config(text="")
        self.show_button.config(state="normal")
        self.wrong_button.config(state="disabled")
        self.correct_button.config(state="disabled")

        done = len(self.words) - len(self.remaining) - 1
        self.progress_label.config(
            text=(
                f"Card {done + 1} / {len(self.words)}   •   "
                f"Session: {self.session_correct} correct, "
                f"{self.session_wrong} wrong"
            )
        )

    def show_definition(self):
        if not self.current_word:
            return

        self.definition_label.config(
            text=self.words[self.current_word]
        )
        self.definition_visible = True

        self.show_button.config(state="disabled")
        self.wrong_button.config(state="normal")
        self.correct_button.config(state="normal")

    def answer(self, correct):
        if not self.current_word:
            return

        stats = self.stats[self.current_word]

        if correct:
            stats.correct += 1
            self.session_correct += 1
        else:
            stats.wrong += 1
            self.session_wrong += 1

        save_stats(self.stats)
        self.next_card()

    def finish_run(self):
        total = self.session_correct + self.session_wrong
        accuracy = (
            self.session_correct / total * 100 if total else 0
        )

        messagebox.showinfo(
            "Run complete",
            f"Run complete!\n\n"
            f"Correct: {self.session_correct}\n"
            f"Wrong: {self.session_wrong}\n"
            f"Accuracy: {accuracy:.1f}%",
        )

        self.current_word = None
        self.word_label.config(text="Run complete")
        self.definition_label.config(
            text="Choose a new run to continue."
        )
        self.progress_label.config(text="")

        self.show_button.config(state="disabled")
        self.wrong_button.config(state="disabled")
        self.correct_button.config(state="disabled")

    def show_stats(self):
        rows = []

        for word, definition in self.words.items():
            s = self.stats[word]
            rows.append(
                (
                    s.problem_score,
                    word,
                    s.correct,
                    s.wrong,
                    s.attempts,
                    s.accuracy,
                )
            )

        rows.sort(reverse=True)

        lines = [
            "WORD                    OK    WRONG   ACCURACY   SCORE",
            "-" * 62,
        ]

        for score, word, correct, wrong, attempts, accuracy in rows:
            lines.append(
                f"{word[:20]:20}  "
                f"{correct:3}   {wrong:5}   "
                f"{accuracy * 100:7.1f}%   {score:.3f}"
            )

        stats_window = tk.Toplevel(self.root)
        stats_window.title("Vocabulary Statistics")
        stats_window.geometry("720x600")

        text = tk.Text(stats_window, font=("Courier New", 11))
        text.pack(fill="both", expand=True, padx=10, pady=10)

        text.insert("1.0", "\n".join(lines))
        text.config(state="disabled")

    def reload_words(self):
        old_words = self.words
        self.words = load_words()

        for word in self.words:
            self.stats.setdefault(word, WordStats())

        # Keep statistics for words that still exist.
        self.stats = {
            word: self.stats[word]
            for word in self.words
        }

        save_stats(self.stats)

        messagebox.showinfo(
            "Words reloaded",
            f"Loaded {len(self.words)} words."
        )
        self.start_run(self.mode)


if __name__ == "__main__":
    root = tk.Tk()
    app = VocabApp(root)
    root.mainloop()
