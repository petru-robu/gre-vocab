# GRE Vocabulary Trainer

A desktop flashcard app (Python + Tkinter, no third-party packages) for learning the **250 most commonly listed GRE words**, split into **10 levels of 25 words, from easiest to hardest**.

## Run

```bash
python vocab_app.py
```

Needs Python 3 with Tkinter. Progress is saved after every answer to `vocab_progress.json`.

## How to study with it

1. **Learn** a level (25 words). A card shows the word; recall the meaning, reveal the answer, then press **Yes** (I knew it) or **No**. A missed card comes back a few cards later until you get it.
2. **Practice** a level when you come back to it (the *Practice…* button on its card):
   - **Weakest words**: the N words from the chosen levels that you know least, based on your answers so far.
   - **Random sample**: N random words from the chosen levels.
3. **Mixed practice** (bottom left) does the same across any set of levels, e.g. all 250 words.
4. After a session, **Practice the missed** drills just the words you got wrong.

Each answer card also shows the part of speech, synonyms (the GRE tests words in synonym clusters), an example sentence, and a warning for look-alikes such as *disinterested / uninterested* or *enervate / energize*.

| Key | Action |
| --- | --- |
| `Space` / `Enter` | Show answer |
| `Y` or `→` | Yes, I knew it |
| `N` or `←` | No, didn't know |
| `U` or `Backspace` | Undo last answer |
| `Esc` | End the session |

A word is **known** after 3 "knew it" answers in a row, **learning** if you've answered it but not reached that, and **new** otherwise. Only your *first* answer to a word in a session is recorded; the retry of a missed card is practice only, since getting it right 30 seconds later says little about long-term memory.

"Weakest" ranks words by a recency-weighted miss rate: recent answers count more, and a single lucky guess does not make a word look solid.

**Statistics & word list** shows every word with its counts and last answers (click a word for its full card). **Progress → Reset…** wipes a level or everything.

## Where the words come from

Nothing was invented. Ten published GRE lists were merged and each word scored by how many lists contain it (lists flagged as high-frequency count more), so a word only makes the deck if many independent sources agree. Every one of the 250 words appears on at least 5 of the 10 lists.

| List | Weight |
| --- | --- |
| [PowerScore "Repeat Offenders"](https://help.powerscore.com/sites/default/files/2021-12/Repeat-Offenders-Vocabulary.pdf) (700 words PowerScore flags as recurring on the GRE) | 2 |
| [Barron's GRE High-Frequency 333](https://www.vocabulary.com/lists/182204) | 1 |
| [Magoosh GRE 1000, "Common (High-frequency)" tier](https://s3.amazonaws.com/magoosh.resources/magoosh-gre-1000-words_oct01.pdf) | 1 |
| GregMat high-frequency list | 1 |
| [PrepScholar GRE vocabulary](https://www.prepscholar.com/gre/blog/gre-vocabulary-list-words/) | 1 |
| [Princeton Review "Hit Parade"](https://www.vocabulary.com/lists/162927) | 1 |
| Magoosh GRE 1000 (all tiers), Manhattan Prep 1000, Greenlight Basic 500, Vocabulary.com GRE Top 1000 | 0.5 each |

Most lists were collected via the [Xatta-Trone/gre-words-collection](https://github.com/Xatta-Trone/gre-words-collection) repository. The Magoosh copy was cross-checked against Magoosh's own PDF.

**Levels** are ordered by how common each word is in everyday English ([wordfreq](https://pypi.org/project/wordfreq/); rarer = harder). Level 1 holds words like *aesthetic* and *pragmatic*; level 10 holds *prevaricate*, *propitiate* and *enervate*.

**Definitions, synonyms and example sentences** were written for this app (`tools/entries.txt`), not copied from the books. They include the secondary senses the GRE likes to test (*sanction*, *intimate*, *fawn*, ...). For the 197 deck words that Magoosh also covers, the definitions were checked against theirs for agreement in meaning.

## Files

```text
vocab_app.py            the app (UI)
vocab_core.py           deck, progress, scoring and session logic (no UI)
data/gre_core_250.json  the deck: 10 levels x 25 words
vocab_progress.json     your progress (created on first answer)
tests/                  python -m unittest discover -s tests
tools/                  how the deck was built (sources, content, build script)
legacy/                 your previous words.txt and vocab_stats.json
```

On first run, answer counts from your old `vocab_stats.json` are carried over for words that are also in the new deck.

## Rebuilding the deck

```bash
pip install wordfreq                       # only needed for rebuilding
python tools/build_wordlist.py             # rewrite data/gre_core_250.json
python tools/build_wordlist.py --list      # preview the selection per level
python tools/build_wordlist.py --fetch     # re-download the source lists first
```

To change the deck size or weights, edit `N_WORDS` / `SOURCES` in the script and add a line to `tools/entries.txt` for any new word (the script tells you which are missing).
