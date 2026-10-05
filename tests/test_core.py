import json
import random
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vocab_core import (  # noqa: E402
    DECK_FILE, Deck, Progress, Session, WordProgress, learn_queue, practice_queue, KNOWN_STREAK,
)

DECK = Deck.load()
NOW = datetime(2026, 10, 5, 12, 0, 0)


def fresh_progress():
    tmp = tempfile.mkdtemp()
    return Progress(Path(tmp) / "progress.json")


class DeckTests(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(len(DECK.words), 250)
        self.assertEqual([len(b.words) for b in DECK.batches], [25] * 10)
        self.assertEqual(len({w for b in DECK.batches for w in b.words}), 250)

    def test_every_word_is_complete(self):
        for w in DECK.words.values():
            self.assertTrue(w.definition and w.example and w.pos, w.text)
            self.assertGreaterEqual(len(w.synonyms), 2, w.text)
            self.assertEqual(DECK.batch(w.batch).words.count(w.text), 1, w.text)

    def test_every_word_is_on_several_source_lists(self):
        # selection rule: nothing in the deck should rest on one or two lists
        self.assertGreaterEqual(min(w.lists for w in DECK.words.values()), 5)

    def test_batches_get_harder(self):
        zipf = json.loads(DECK_FILE.read_text(encoding="utf-8"))["words"]
        means = [sum(zipf[w]["zipf"] for w in b.words) / 25 for b in DECK.batches]
        self.assertEqual(means, sorted(means, reverse=True))


class WordProgressTests(unittest.TestCase):
    def test_status_transitions(self):
        p = WordProgress()
        self.assertEqual(p.status, "new")
        p.record(True, NOW)
        self.assertEqual(p.status, "learning")
        for _ in range(KNOWN_STREAK - 1):
            p.record(True, NOW)
        self.assertEqual(p.status, "known")
        p.record(False, NOW)
        self.assertEqual(p.status, "learning")
        self.assertEqual(p.streak, 0)

    def test_weakness_order(self):
        def w(history):
            p = WordProgress()
            for ch in history:
                p.record(ch == "1", NOW)
            return p.weakness
        self.assertGreater(w("0"), w("1"))
        self.assertGreater(w("0"), w("01"))           # recovered once -> less weak
        self.assertGreater(w("10"), w("01"))          # recent miss counts more than an old one
        self.assertGreater(w("1"), w("111"))          # more evidence of knowing -> stronger
        self.assertGreater(w("0000"), w("0"))         # repeated misses are weaker still
        self.assertEqual(WordProgress().weakness, 0.5)

    def test_history_is_capped(self):
        p = WordProgress()
        for _ in range(30):
            p.record(True, NOW)
        self.assertEqual(len(p.history), 10)
        self.assertEqual(p.correct, 30)

    def test_imported_counts_without_history(self):
        p = WordProgress(correct=1, wrong=3)
        self.assertEqual(p.status, "learning")
        self.assertGreater(p.weakness, WordProgress(correct=3, wrong=1).weakness)


class SessionTests(unittest.TestCase):
    def make(self, words, **kw):
        progress = fresh_progress()
        return Session(DECK, progress, words, "t", rng=random.Random(1), **kw), progress

    def test_correct_answers_finish_the_session(self):
        s, p = self.make(["abate", "lucid"])
        s.answer(True)
        s.answer(True)
        self.assertTrue(s.is_done)
        self.assertEqual((s.known_count, s.missed_count), (2, 0))
        self.assertEqual(p.get("lucid").correct, 1)

    def test_missed_word_returns_and_only_first_answer_is_recorded(self):
        s, p = self.make(["lucid", "banal", "tacit", "terse"])
        s.answer(False)                       # miss lucid
        self.assertIn("lucid", s.queue)
        while s.current != "lucid":
            s.answer(True)
        self.assertTrue(s.is_retry)
        s.answer(True)                        # right on the retry
        self.assertNotIn("lucid", s.queue)
        self.assertEqual(s.missed_words, ["lucid"])
        self.assertEqual((p.get("lucid").correct, p.get("lucid").wrong), (0, 1))

    def test_missed_word_keeps_coming_back_until_right(self):
        s, _ = self.make(["lucid"])
        for _ in range(4):
            s.answer(False)
            self.assertEqual(s.current, "lucid")
        s.answer(True)
        self.assertTrue(s.is_done)

    def test_repeat_off_does_not_requeue(self):
        s, _ = self.make(["lucid", "banal"], repeat_missed=False)
        s.answer(False)
        s.answer(True)
        self.assertTrue(s.is_done)

    def test_undo_restores_queue_stats_and_daily_count(self):
        s, p = self.make(["lucid", "banal"])
        s.answer(False)
        self.assertEqual(p.get("lucid").wrong, 1)
        self.assertEqual(p.today()[0], 1)
        self.assertTrue(s.undo())
        self.assertEqual(s.current, "lucid")
        self.assertEqual(s.queue, ["lucid", "banal"])
        self.assertEqual(p.get("lucid").attempts, 0)
        self.assertNotIn("lucid", p.words)
        self.assertEqual(p.today()[0], 0)
        self.assertFalse(s.undo())

    def test_undo_a_second_answer_keeps_the_first(self):
        s, p = self.make(["lucid", "banal"])
        s.answer(True)
        s.answer(False)
        s.undo()
        self.assertEqual(p.get("lucid").correct, 1)
        self.assertEqual(p.get("banal").attempts, 0)
        self.assertEqual(s.current, "banal")


class QueueTests(unittest.TestCase):
    def test_learn_queue_has_whole_level_with_unseen_first(self):
        p = fresh_progress()
        level = DECK.batch(2).words
        for w in level[:5]:
            p.record(w, True)
        q = learn_queue(DECK, p, 2, random.Random(3))
        self.assertEqual(sorted(q), sorted(level))
        self.assertEqual(set(q[-5:]), set(level[:5]))

    def test_weak_practice_picks_the_weakest_seen_words(self):
        p = fresh_progress()
        level = DECK.batch(1).words
        for w in level[:10]:
            p.record(w, True)
            p.record(w, True)
            p.record(w, True)
        for w in level[10:13]:
            p.record(w, False)
        q = practice_queue(DECK, p, [1], "weak", 3, random.Random(0))
        self.assertEqual(set(q), set(level[10:13]))

    def test_weak_practice_ignores_unseen_words(self):
        p = fresh_progress()
        p.record(DECK.batch(1).words[0], False)
        q = practice_queue(DECK, p, [1], "weak", 10, random.Random(0))
        self.assertEqual(q, [DECK.batch(1).words[0]])
        self.assertEqual(practice_queue(DECK, fresh_progress(), [1], "weak", 10), [])

    def test_random_practice_samples_across_levels(self):
        p = fresh_progress()
        q = practice_queue(DECK, p, [1, 5, 10], "random", 20, random.Random(0))
        self.assertEqual(len(q), 20)
        self.assertEqual(len(set(q)), 20)
        allowed = set(DECK.batch(1).words) | set(DECK.batch(5).words) | set(DECK.batch(10).words)
        self.assertLessEqual(set(q), allowed)
        self.assertEqual(len(practice_queue(DECK, p, [3], "random", None)), 25)
        self.assertEqual(len(practice_queue(DECK, p, [3], "random", 99)), 25)


class PersistenceTests(unittest.TestCase):
    def test_round_trip(self):
        p = fresh_progress()
        p.record("lucid", True, NOW)
        p.record("lucid", False, NOW)
        p.settings["repeat_missed"] = False
        p.add_study_time(125, NOW)
        p.save()
        q = Progress.load(p.path)
        self.assertEqual(q.get("lucid").history, "10")
        self.assertEqual((q.get("lucid").correct, q.get("lucid").wrong), (1, 1))
        self.assertFalse(q.settings["repeat_missed"])
        self.assertEqual(q.today(NOW.date()), (2, 125))

    def test_corrupt_file_is_kept_aside(self):
        p = fresh_progress()
        p.path.write_text("{ not json")
        q = Progress.load(p.path)
        self.assertEqual(q.words, {})
        self.assertTrue(p.path.with_suffix(".corrupt").exists())

    def test_legacy_import_keeps_only_deck_words(self):
        tmp = Path(tempfile.mkdtemp())
        legacy = tmp / "old.json"
        legacy.write_text(json.dumps({
            "abate": {"correct": 0, "wrong": 2},     # not in the deck's 250
            "lucid": {"correct": 2, "wrong": 1},
            "technocrat": {"correct": 1, "wrong": 0},  # personal word, not in the deck
            "banal": {"correct": 0, "wrong": 0},     # never answered
        }))
        p = Progress.load(tmp / "new.json", deck=DECK, legacy_file=legacy)
        self.assertEqual(set(p.words), {"lucid"})
        self.assertEqual(p.migrated, 1)
        self.assertTrue((tmp / "new.json").exists())
        # a second load reads the new file and does not import again
        legacy.write_text("{}")
        self.assertEqual(set(Progress.load(tmp / "new.json", deck=DECK, legacy_file=legacy).words), {"lucid"})

    def test_day_streak(self):
        p = fresh_progress()
        today = date(2026, 10, 5)
        self.assertEqual(p.day_streak(today), 0)
        for back in (1, 2, 3):                       # yesterday and before, nothing yet today
            p.daily[(today - timedelta(days=back)).isoformat()] = {"answers": 4, "seconds": 60}
        self.assertEqual(p.day_streak(today), 3)
        p.daily[today.isoformat()] = {"answers": 1, "seconds": 5}
        self.assertEqual(p.day_streak(today), 4)
        p.daily[(today - timedelta(days=5)).isoformat()] = {"answers": 4, "seconds": 60}  # gap -> not counted
        self.assertEqual(p.day_streak(today), 4)

    def test_counts_and_reset(self):
        p = fresh_progress()
        words = DECK.batch(1).words
        for _ in range(3):
            p.record(words[0], True)
        p.record(words[1], False)
        self.assertEqual(p.counts(words), {"known": 1, "learning": 1, "new": 23})
        p.reset(words[:2])
        self.assertEqual(p.counts(words), {"known": 0, "learning": 0, "new": 25})


if __name__ == "__main__":
    unittest.main()
