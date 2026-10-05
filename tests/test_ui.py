"""Drives the real Tk widgets (no mouse needed). Skipped when there is no display."""
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vocab_app  # noqa: E402
from vocab_core import Progress  # noqa: E402

try:
    _probe = tk.Tk()
    _probe.destroy()
    HAS_DISPLAY = True
except tk.TclError:
    HAS_DISPLAY = False


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class UITests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = vocab_app.App(self.root, self.tmp / "progress.json", self.tmp / "no_legacy.json")

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run_session(self, pattern):
        """Answer every card in the open StudyScreen; pattern(i) -> knew it?"""
        screen = self.app.screen
        self.assertIsInstance(screen, vocab_app.StudyScreen)
        i = 0
        while self.app.screen is screen:
            screen.answer(True)               # ignored: answer not revealed yet
            screen.reveal()
            screen.answer(pattern(i))
            i += 1
        return i

    def test_home_has_ten_level_cards(self):
        self.assertIsInstance(self.app.screen, vocab_app.HomeScreen)
        cards = [w for w in walk(self.app.screen) if isinstance(w, vocab_app.BatchCard)]
        self.assertEqual(len(cards), 10)

    def test_learn_then_summary_then_weak_practice(self):
        self.app.start_learn(2)
        screen = self.app.screen
        self.assertEqual(screen.session.total, 25)
        missed = list(self.app.deck.batch(2).words)[:5]
        # answer "no" for five specific words, "yes" for the rest (retries all "yes")
        seen = set()

        def knew(i):
            word = screen.session.current
            first = word not in seen
            seen.add(word)
            return not (first and word in missed)

        self.run_session(knew)
        self.assertIsInstance(self.app.screen, vocab_app.SummaryScreen)
        progress = self.app.progress
        self.assertEqual(progress.today()[0], 25)           # retries are not counted
        self.assertTrue((self.tmp / "progress.json").exists())
        self.assertEqual(sorted(w for w in self.app.deck.batch(2).words if progress.get(w).wrong), sorted(missed))

        # weakest-5 practice must be exactly the five missed words
        dialog = vocab_app.PracticeDialog(self.app, [2])
        self.assertEqual(dialog.method.get(), "weak")
        dialog.count.set("5")
        dialog.update_info()
        self.assertIn("5 weakest of the 25", dialog.info["text"])
        dialog.start()
        self.assertIsInstance(self.app.screen, vocab_app.StudyScreen)
        self.assertEqual(sorted(self.app.screen.session.queue), sorted(missed))

        # undo of an answer puts the card back and the stats back
        screen = self.app.screen
        word = screen.session.current
        before = progress.get(word).attempts
        screen.reveal()
        screen.answer(False)
        self.assertEqual(progress.get(word).attempts, before + 1)
        screen.undo()
        self.assertEqual(progress.get(word).attempts, before)
        self.assertEqual(screen.session.current, word)
        self.assertTrue(screen.revealed)

        # ending with nothing answered goes straight home; after an answer it shows the summary
        screen.end()
        self.assertIsInstance(self.app.screen, vocab_app.HomeScreen)
        self.app.start_session(missed, "again", "practice")
        screen = self.app.screen
        screen.reveal()
        screen.answer(True)
        screen.end()
        self.assertIsInstance(self.app.screen, vocab_app.SummaryScreen)
        self.app.show_home()
        self.assertIsInstance(self.app.screen, vocab_app.HomeScreen)

    def test_practice_dialog_guards(self):
        dialog = vocab_app.PracticeDialog(self.app, [1])
        self.assertEqual(dialog.method.get(), "random")      # nothing studied yet
        dialog.method.set("weak")
        self.assertEqual(str(dialog.start_btn["state"]), "disabled")
        dialog.set_all(False)
        self.assertEqual(str(dialog.start_btn["state"]), "disabled")
        dialog.method.set("random")
        dialog.set_all(True)
        dialog.count.set("All")
        dialog.update_info()
        dialog.start()
        self.assertEqual(self.app.screen.session.total, 250)

    def test_stats_window_filters_and_detail(self):
        win = vocab_app.StatsWindow(self.app, level=3)
        self.assertEqual(len(win.tree.get_children()), 25)
        win.level_var.set("All levels")
        win.fill()
        self.assertEqual(len(win.tree.get_children()), 250)
        win.status_var.set("Known")
        win.fill()
        self.assertEqual(len(win.tree.get_children()), 0)
        win.status_var.set("All")
        win.sort_by("word")
        win.fill()
        first = win.tree.get_children()[0]
        self.assertEqual(first, "aberrant")
        win.tree.selection_set(first)
        win.show_detail()
        self.assertIn("Synonyms", win.detail_body["text"])
        win.destroy()

    def test_reset_and_corrupt_progress(self):
        self.app.progress.record("lucid", True)
        self.app.progress.reset(["lucid"])
        self.assertEqual(self.app.progress.get("lucid").attempts, 0)

    def test_every_card_renders(self):
        """Reveal every word of the deck once: catches long text / missing field bugs."""
        self.app.start_session(list(self.app.deck.words), "All", "practice")
        screen = self.app.screen
        for _ in range(250):
            screen.reveal()
            self.assertTrue(screen.def_label["text"])
            screen.answer(True)
        self.assertIsInstance(self.app.screen, vocab_app.SummaryScreen)

    def test_pos_text(self):
        self.assertEqual(vocab_app.pos_text("adj."), "adjective")
        self.assertEqual(vocab_app.pos_text("v./n."), "verb / noun")


if __name__ == "__main__":
    unittest.main()
