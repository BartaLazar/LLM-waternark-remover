"""Walk a text and swap every N-th word for its closest synonym."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .inflect import match_case
from .synonyms import SynonymFinder
from .tokens import detokenize, tokenize


@dataclass
class Replacement:
    position: int  # 1-based index among words, counting every word in the text
    original: str
    replacement: str
    similarity: float  # Wu-Palmer score against the word's dominant sense; see SynonymFinder


def rewrite(
    text: str,
    every: int = 5,
    senses: int = 1,
    allow_multiword: bool = False,
    slide: bool = False,
    threshold: float = 0.95,
    finder: Optional[SynonymFinder] = None,
) -> Tuple[str, List[Replacement]]:
    """Return the rewritten text and the list of substitutions made.

    Every `every`-th word is looked up. Words with no usable synonym -- function
    words, names, anything WordNet does not cover, or a sense too dissimilar to
    the word's dominant meaning to clear `threshold` (see `SynonymFinder`) --
    are left alone; with `slide=True` the search moves on to the following word
    instead, which keeps the substitution rate close to 1-in-N.
    """
    if every < 1:
        raise ValueError("every must be >= 1")

    from nltk import pos_tag

    finder = finder or SynonymFinder(senses=senses, allow_multiword=allow_multiword, threshold=threshold)
    tokens = tokenize(text)
    # Positions of the real words within the full token list; gaps are ignored
    # for counting but stay in `tokens` so the output keeps its formatting.
    word_indices = [i for i, token in enumerate(tokens) if token.is_word]
    if not word_indices:
        return text, []

    # Tag once for the whole text: a word's part of speech depends on the words
    # around it ("results" the noun vs "results" the verb).
    tags = pos_tag([tokens[i].text for i in word_indices])
    replacements: List[Replacement] = []
    next_target = every  # 1-based ordinal of the next word to attempt

    for ordinal, token_index in enumerate(word_indices, start=1):
        if ordinal < next_target:
            continue
        original = tokens[token_index].text
        found = finder.find(original, tags[ordinal - 1][1])
        if found is None:
            # Hold the slot open for the next word, or skip to the next
            # multiple of N and accept a missed substitution.
            if not slide:
                next_target = ordinal + every
            continue
        synonym, similarity = found
        tokens[token_index].text = match_case(original, synonym)
        replacements.append(Replacement(ordinal, original, tokens[token_index].text, similarity))
        # Measure the next interval from where we actually landed, so sliding
        # never bunches two substitutions closer than N words apart.
        next_target = ordinal + every

    return detokenize(tokens), replacements
