# GRE Vocabulary Trainer

A small desktop flashcard app built with Python and Tkinter.

## Run

1. Make sure Python 3 is installed.
2. Put `vocab_app.py` and `words.txt` in the same folder.
3. Run:

```bash
python vocab_app.py
```

No third-party packages are required.

## Add vocabulary

Edit `words.txt` using:

    word = definition

For example:

    mendacious = dishonest; lying
    laconic = using very few words
    obfuscate = make something unclear or difficult to understand

You can add as many words as you want.

## How it works

### Random Run
Each word appears once in a shuffled run.

Click **Show Definition**, then:
- **OK / I Knew It** if you knew the definition
- **Wrong / Didn't Know** if you did not

The app stores correct and wrong counts in `vocab_stats.json`.

### Problem Words Run
This mode uses the statistics to weight the cards.

Words that you frequently get wrong appear more often. Unseen words also receive a reasonable chance of appearing.

The score is:

    (wrong + 1) / (attempts + 2)

Higher score = more problematic.

The statistics persist after closing the application.
