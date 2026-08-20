# synreplace

A small CLI that takes a text and gives it back with every N-th word swapped for
its closest synonym. Synonyms come from **WordNet** via NLTK — everything runs
offline, no API key, no network after the first run.

```
$ synreplace -n 3 --slide "The quick brown fox jumps over the lazy dog while the researchers carefully examined the surprising results of their difficult experiment."
The quick brown fox leaps over the lazy dog while the investigators carefully examined the surprising effects of their hard experiment.
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

The WordNet data (~10 MB) downloads itself on the first run, along with the
CMU Pronouncing Dictionary (used for accurate consonant-doubling like "occur"
→ "occurring"; optional -- inflection just falls back to a cruder heuristic
if it can't be fetched).

Also want the [web interface](web/)? Same venv, one more command:

```bash
pip install -r requirements.txt
```

## Usage

```
synreplace [-n N] [--slide] [--senses K] [--threshold T] [--multiword] [-v]
           [-c | -i FILE | -o FILE | TEXT]
```

Input is taken from the first of these that applies:

| Source | How |
| --- | --- |
| Clipboard | `synreplace --clip -n 4` — reads the clipboard, writes the result back to it and prints it |
| File | `synreplace -i draft.txt` — writes `draft-modified.txt` next to it, or `-o FILE` to name it yourself |
| Argument | `synreplace -n 3 "some text here"` — printed to stdout |
| Pipe | `cat draft.md \| synreplace -n 5 > out.md` |
| Interactive | run it bare, paste, then press `Ctrl-D` |

### Options

| Flag | Meaning |
| --- | --- |
| `-n, --every N` | Replace every N-th word (default `5`) |
| `--slide` | If the N-th word has no synonym, try the next word instead (recommended) |
| `--senses K` | Consider the K closest senses of the word, not just the closest (default `1`) |
| `--threshold T` | Minimum sense similarity (`0`-`1`) a `--senses` candidate must clear (default `0.95`); `0` disables the check — see below |
| `--multiword` | Allow multi-word synonyms such as "give up" |
| `-v, --verbose` | List every substitution on stderr, with its sense similarity |
| `-c, --clip` | Read from and write back to the clipboard |
| `-i, --input` / `-o, --output` | Read from / write to a file. With `-i` alone, output goes to `<name>-modified.<ext>` next to the input file |

Without `--slide`, a missed word is just skipped — substitutions land only on
exact multiples of N, so the count is often well under 1-in-N. With `--slide`,
a miss moves the search to the next word, keeping the rate close to 1-in-N
(substitutions still stay at least N words apart).

## How a synonym is picked

1. The whole text is part-of-speech tagged, so "results" the noun and "results"
   the verb are treated differently.
2. The word is reduced to its lemma (`researchers` → `researcher`).
3. WordNet orders a word's senses by how common they are. `--senses 1` uses only
   the most common one, which is what keeps replacements on-meaning; `--senses K`
   also considers the next `K-1` senses, subject to `--threshold`.
4. Among every candidate gathered across those senses, the one with the
   *highest similarity* to the word's single most common sense wins — not
   whichever sense happens to be listed first. Ties break by corpus frequency,
   then alphabetically, so the tool is fully deterministic.
5. The synonym is put back into the original word's form and capitalisation —
   `expressed` → `evinced`, `Researchers` → `Investigators`.

Nothing else in the text moves: whitespace, newlines, punctuation and numbers
come out byte-identical. `-v` prints each substitution's sense similarity
against the word's dominant meaning (see `--threshold` below) — always 100%
at the default `--senses 1`:

```
  #12 researchers -> investigators (100% similar)
```

## `--threshold`: how far a synonym is allowed to drift

`--senses K` (K > 1) lets a word borrow synonyms from its 2nd, 3rd, ... most
common sense, not just its dominant one — useful for variety, but those senses
can be barely related to what the word actually means in context (`fox` in its
dominant sense is the animal; a rarer sense is "a person who dodges/evades",
giving `dodger`).

`--threshold` guards against that: each candidate sense is scored against the
word's *dominant* sense using WordNet's Wu-Palmer similarity (0-1, based on
how close their nearest common ancestor is in the meaning hierarchy), and any
sense scoring below the threshold is dropped — the word falls through to
skip/slide like it had no synonym at all, the same as any other unusable word.

```
$ synreplace -n 1 --slide --senses 3 --threshold 0 -v "the quick brown fox jumps over the lazy dog"
  #2 quick -> speedy (100% similar)
  #4 fox -> dodger (48% similar)
  #5 jumps -> leaps (100% similar)
  #8 lazy -> indolent (50% similar)
  #9 dog -> frump (60% similar)
5 substitutions

$ synreplace -n 1 --slide --senses 3 --threshold 0.95 -v "the quick brown fox jumps over the lazy dog"
  #2 quick -> speedy (100% similar)
  #5 jumps -> leaps (100% similar)
2 substitutions   # fox, lazy and dog are left alone — their only candidates scored below 95%
```

A word's dominant sense is always 100% similar to itself, so **the default
`--threshold 0.95` has no effect at the default `--senses 1`** — it only starts
rejecting candidates once `--senses` is raised above `1`.

## What is deliberately left alone

The tool prefers leaving a word alone over producing a wrong one:

- **Function words and names** — determiners, pronouns, prepositions,
  conjunctions, auxiliaries and proper nouns are never touched.
- **Comparatives and superlatives** (`bigger`, `best`) — their synonyms cannot be
  re-inflected reliably.
- **Irregular forms.** If a candidate synonym inflects irregularly and the
  regular guess would be wrong (`go` → `goed`, `foot` → `foots`), that candidate
  is skipped rather than mangled. WordNet's own exception lists supply this.
- **Words WordNet has no distinct synonym for**, which is a lot of them.

This is why plain `-n 3` often produces fewer substitutions than you would
expect. See `--slide` above for the fix.

## Quality note

WordNet has no idea what your sentence is about. It picks the most common sense,
which is right most of the time and occasionally not (`problem` → `job`). Read
the output before using it; `-v` shows you exactly what changed.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Web interface

A browser UI and REST API also exist, in [`web/`](web/) — a separate,
self-contained folder with its own setup and its own server, independent of
this CLI. See [`web/README.md`](web/README.md) to run it, and
[`web/docs/API.md`](web/docs/API.md) for the REST API reference.
