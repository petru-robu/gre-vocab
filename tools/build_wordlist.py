#!/usr/bin/env python3
"""Build data/gre_core_250.json - the deck used by vocab_app.py.

How the deck is made (nothing here is invented):

1. SELECTION - which words?
   Ten published GRE word lists (see SOURCES; cached in tools/sources/) are
   merged. A word scores the sum of the weights of the lists it appears on, so
   words that many independent lists agree on rank first. Close variants
   (castigation -> castigate, ...) are merged first via ALIASES.
   Ties are broken by number of lists, then by how common the word is in
   everyday English (GRE passages are drawn from real prose).

2. DIFFICULTY - which batch?
   The selected words are ordered from most to least common in everyday
   English (wordfreq's Zipf scale: rarer = harder) and cut into batches of
   BATCH_SIZE, so batch 1 is the most approachable and batch 10 the hardest.

3. CONTENT - tools/entries.txt holds the definition, synonyms and example
   sentence of every word (one line per word: word | pos | definition |
   synonyms | example [| note]).

Usage:
    pip install wordfreq            # only needed to (re)build the deck
    python tools/build_wordlist.py            # write data/gre_core_250.json
    python tools/build_wordlist.py --list     # just print the selection
    python tools/build_wordlist.py --fetch    # re-download the source lists
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "tools" / "sources"
ENTRIES_FILE = ROOT / "tools" / "entries.txt"
OUT_FILE = ROOT / "data" / "gre_core_250.json"

N_WORDS = 250
BATCH_SIZE = 25

RAW = "https://raw.githubusercontent.com/Xatta-Trone/gre-words-collection/master/word-list/"
COLLECTION = "https://github.com/Xatta-Trone/gre-words-collection"

# id -> (display name, url, weight, file in the Xatta-Trone collection or None)
SOURCES = {
    "powerscore": (
        "PowerScore GRE Vocabulary: Repeat Offenders (700 words PowerScore flags as recurring on the GRE)",
        "https://help.powerscore.com/sites/default/files/2021-12/Repeat-Offenders-Vocabulary.pdf",
        2.0, "005%20PowerscoreRepeatOffenders-699.csv"),
    "barrons333": (
        "Barron's GRE High-Frequency 333 words",
        "https://www.vocabulary.com/lists/182204", 1.0, None),
    "magoosh_common": (
        "Magoosh GRE 1000 - Common (High-frequency) words",
        "https://s3.amazonaws.com/magoosh.resources/magoosh-gre-1000-words_oct01.pdf",
        1.0, "004%20Magoosh_Common-309.csv"),
    "gregmat": (
        "GregMat high-frequency GRE words",
        COLLECTION, 1.0, "001%20GregMat960.csv"),
    "prepscholar": (
        "PrepScholar GRE vocabulary list",
        "https://www.prepscholar.com/gre/blog/gre-vocabulary-list-words/",
        1.0, "002%20Prepscholar357.csv"),
    "hit_parade": (
        "Princeton Review 'Hit Parade' (most frequently tested GRE words)",
        "https://www.vocabulary.com/lists/162927", 1.0, None),
    "magoosh_1000": (
        "Magoosh GRE 1000 words (all tiers)",
        "https://s3.amazonaws.com/magoosh.resources/magoosh-gre-1000-words_oct01.pdf",
        0.5, "008%20Magoosh-1000.csv"),
    "manhattan": (
        "Manhattan Prep 1000 GRE words",
        COLLECTION, 0.5, "013%20Manhattan-Prep-1000-GRE-Words-Definitions.csv"),
    "greenlight": (
        "Greenlight Test Prep GRE Basic 500",
        "https://quizlet.com/18795939/gre-basic-flash-cards/",
        0.5, "007%20Greenlight-Vocab-List-Basic-500.csv"),
    "vocabcom": (
        "Vocabulary.com GRE Top 1000",
        COLLECTION, 0.5, "012%20The%20Vocabulary.com%20Top%201000%EF%BB%BF.csv"),
}

# Inflected / derived forms counted as the same word as their head word.
# (Genuinely different words such as discrete/discreet or prodigal/prodigious
# are deliberately not merged.)
ALIASES = {
    "veracious": "veracity", "iconoclastic": "iconoclast", "fallacy": "fallacious",
    "magnanimity": "magnanimous", "anomaly": "anomalous", "avaricious": "avarice",
    "efficacy": "efficacious", "equivocal": "equivocate", "mendacity": "mendacious",
    "perfidy": "perfidious", "anachronism": "anachronistic", "bombast": "bombastic",
    "penurious": "penury", "conciliate": "conciliatory", "intransigence": "intransigent",
    "castigation": "castigate", "ambivalence": "ambivalent", "contention": "contentious",
    "eminence": "eminent", "frugality": "frugal", "reverence": "reverent", "derision": "deride",
    "insularity": "insular", "laudable": "laud", "fawning": "fawn", "verbosity": "verbose",
    "proliferation": "proliferate", "quiescence": "quiescent", "indigence": "indigent",
    "incongruity": "incongruous", "diffidence": "diffident", "lethargy": "lethargic",
    "obsequiousness": "obsequious", "pedantry": "pedantic", "torpid": "torpor",
    "loquacity": "loquacious", "taciturnity": "taciturn", "sagacity": "sagacious",
    "audacity": "audacious", "truculence": "truculent", "ebullience": "ebullient",
    "fastidiousness": "fastidious", "gregariousness": "gregarious",
}

LEVEL_LABELS = [
    "Warm-up", "Easy", "Approachable", "Moderate", "Intermediate",
    "Challenging", "Demanding", "Hard", "Very hard", "Expert",
]


def fetch_sources():
    from urllib.request import urlopen

    for sid, (_, _, _, remote) in SOURCES.items():
        if remote is None:
            print(f"skip {sid} (stored by hand in tools/sources/{sid}.txt)")
            continue
        raw = urlopen(RAW + remote).read().decode("utf-8-sig")
        words = []
        for line in raw.splitlines():
            w = line.strip().lower()
            if w and w.replace("'", "").replace("-", "").replace(" ", "").isalpha() and w not in words:
                words.append(w)
        (SOURCES_DIR / f"{sid}.txt").write_text("\n".join(words) + "\n", encoding="utf-8")
        print(f"{sid}: {len(words)} words")


def read_source(sid):
    return [w for w in (SOURCES_DIR / f"{sid}.txt").read_text(encoding="utf-8").split("\n") if w]


def rank_words(zipf):
    score = defaultdict(float)
    found_in = defaultdict(list)
    for sid, (_, _, weight, _) in SOURCES.items():
        for w in read_source(sid):
            head = ALIASES.get(w, w)
            if sid not in found_in[head]:
                found_in[head].append(sid)
                score[head] += weight
    pool = sorted(score, key=lambda w: (-score[w], -len(found_in[w]), w))[: N_WORDS + 150]
    freq = {w: zipf(w) for w in pool}
    picked = sorted(pool, key=lambda w: (-score[w], -len(found_in[w]), -freq[w], w))[:N_WORDS]
    return picked, score, found_in, freq


def read_entries():
    entries = {}
    for n, raw in enumerate(ENTRIES_FILE.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) not in (5, 6) or not all(parts[:5]):
            sys.exit(f"entries.txt line {n}: expected 'word | pos | definition | synonyms | example [| note]'")
        word, pos, definition, synonyms, example = parts[:5]
        entries[word] = {
            "pos": pos,
            "definition": definition,
            "synonyms": [s.strip() for s in synonyms.split(",") if s.strip()],
            "example": example,
            "note": parts[5] if len(parts) == 6 else "",
        }
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print the selection and exit")
    ap.add_argument("--fetch", action="store_true", help="re-download the source lists first")
    args = ap.parse_args()

    if args.fetch:
        fetch_sources()

    from wordfreq import zipf_frequency

    picked, score, found_in, freq = rank_words(lambda w: zipf_frequency(w, "en"))
    by_difficulty = sorted(picked, key=lambda w: (-freq[w], w))  # most common first = easiest first

    if args.list:
        for b in range(N_WORDS // BATCH_SIZE):
            chunk = by_difficulty[b * BATCH_SIZE:(b + 1) * BATCH_SIZE]
            print(f"--- batch {b + 1}: {', '.join(chunk)}")
        return

    entries = read_entries()
    missing = [w for w in by_difficulty if w not in entries]
    extra = [w for w in entries if w not in set(by_difficulty)]
    if missing or extra:
        sys.exit(f"entries.txt mismatch\n  missing entries for: {missing}\n  entries not in selection: {extra}")

    words, batches = {}, []
    for b in range(N_WORDS // BATCH_SIZE):
        chunk = by_difficulty[b * BATCH_SIZE:(b + 1) * BATCH_SIZE]
        batches.append({"number": b + 1, "label": LEVEL_LABELS[b], "words": chunk})
        for w in chunk:
            words[w] = {
                **entries[w],
                "batch": b + 1,
                "lists": len(found_in[w]),
                "score": round(score[w], 1),
                "zipf": round(freq[w], 2),
            }

    deck = {
        "meta": {
            "title": "GRE Core 250",
            "batch_size": BATCH_SIZE,
            "lists_total": len(SOURCES),
            "selection": "Top words by agreement across published GRE high-frequency lists "
                         "(weighted); batches ordered by everyday-English frequency, easiest first.",
            "sources": [
                {"id": sid, "name": name, "url": url, "weight": weight, "size": len(read_source(sid))}
                for sid, (name, url, weight, _) in SOURCES.items()
            ],
        },
        "batches": batches,
        "words": words,
    }
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(json.dumps(deck, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT_FILE.relative_to(ROOT)}: {len(words)} words in {len(batches)} batches")


if __name__ == "__main__":
    main()
