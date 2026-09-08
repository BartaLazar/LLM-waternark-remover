"""Walk a text and swap every N-th word for its closest synonym."""

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .inflect import fix_article, match_case
from .sources import DEFAULT_SOURCES, make_source
from .tokens import Token, detokenize, tokenize

# Winner + this many extra choices offered alongside it (e.g. for a UI picker).
ALTERNATIVES_LIMIT = 3


@dataclass
class Alternative:
    word: str  # already re-inflected and re-cased to match the original word
    similarity: float  # see Replacement.similarity


@dataclass
class Replacement:
    position: int  # 1-based index among words, counting every word in the text
    original: str
    replacement: str
    similarity: float  # Wu-Palmer score against the word's dominant sense; see SynonymFinder
    alternatives: List[Alternative] = field(default_factory=list)  # other valid choices, best first


def rewrite(
    text: str,
    every: int = 5,
    senses: int = 3,
    allow_multiword: bool = False,
    slide: bool = False,
    threshold: float = 0.95,
    sources: Sequence[str] = DEFAULT_SOURCES,
    finder: Optional[object] = None,
) -> Tuple[str, List[Replacement]]:
    """Return the rewritten text and the list of substitutions made.

    Starting from the first word, every `every`-th word after it is looked up
    (word 1, then `1 + every`, `1 + 2*every`, ...). Words with no usable
    synonym -- function words, names, nothing any enabled source covers, or a
    WordNet sense too dissimilar to the word's dominant meaning to clear
    `threshold` (see `SynonymFinder`) -- are left alone; with `slide=True` the
    search moves on to the following word instead, which keeps the
    substitution rate close to 1-in-N.

    `sources` selects one or more synonym sources by name (see
    `sources.SOURCE_NAMES`) -- with more than one, candidates from every
    enabled source are pooled together (see `sources.CompositeSource`).
    Ignored if `finder` is given explicitly.
    """
    tokens, replacements = rewrite_tokens(
        text, every=every, senses=senses, allow_multiword=allow_multiword,
        slide=slide, threshold=threshold, sources=sources, finder=finder,
    )
    return detokenize(tokens), replacements


def rewrite_tokens(
    text: str,
    every: int = 5,
    senses: int = 3,
    allow_multiword: bool = False,
    slide: bool = False,
    threshold: float = 0.95,
    sources: Sequence[str] = DEFAULT_SOURCES,
    finder: Optional[object] = None,
) -> Tuple[List[Token], List[Replacement]]:
    """Same substitution as `rewrite()`, but returns the full token list
    (words *and* the gaps between them) instead of the joined string.

    Useful for a caller -- e.g. the web UI -- that wants to edit individual
    words after the fact (reset one back to its original, swap in a different
    alternative) and rebuild the text itself: `detokenize(tokens)` recovers
    exactly what `rewrite()` would have returned.
    """
    if every < 1:
        raise ValueError("every must be >= 1")

    from nltk import pos_tag

    finder = finder or make_source(sources, senses=senses, allow_multiword=allow_multiword, threshold=threshold)
    tokens = tokenize(text)
    # Positions of the real words within the full token list; gaps are ignored
    # for counting but stay in `tokens` so the output keeps its formatting.
    word_indices = [i for i, token in enumerate(tokens) if token.is_word]
    if not word_indices:
        return tokens, []

    # Tag once for the whole text: a word's part of speech depends on the words
    # around it ("results" the noun vs "results" the verb).
    tags = pos_tag([tokens[i].text for i in word_indices])
    replacements: List[Replacement] = []
    next_target = 1  # 1-based ordinal of the next word to attempt; starts at the first word

    for ordinal, token_index in enumerate(word_indices, start=1):
        if ordinal < next_target:
            continue
        original = tokens[token_index].text
        found = finder.find_top(original, tags[ordinal - 1][1], limit=1 + ALTERNATIVES_LIMIT)
        if not found:
            # Hold the slot open for the next word, or skip ahead N words on
            # the grid and accept a missed substitution.
            if not slide:
                next_target = ordinal + every
            continue
        synonym, similarity = found[0]
        alternatives = [Alternative(match_case(original, word), sim) for word, sim in found[1:]]
        tokens[token_index].text = match_case(original, synonym)
        replacements.append(
            Replacement(ordinal, original, tokens[token_index].text, similarity, alternatives)
        )
        # A synonym swap can change whether the word now starts with a vowel
        # sound, stranding "a"/"an" on the wrong side of it ("a single
        # discovery" -> "a individual discovery"): fix the immediately
        # preceding word if it's actually that article. Not itself recorded
        # as a Replacement -- like re-inflection, it's a grammatical
        # side-effect of this substitution, not a substitution of its own.
        if ordinal >= 2:
            article_token = tokens[word_indices[ordinal - 2]]
            if article_token.text.lower() in ("a", "an"):
                fixed = fix_article(article_token.text, tokens[token_index].text)
                if fixed != article_token.text:
                    article_token.original_text = article_token.text
                    article_token.text = fixed
        # Measure the next interval from where we actually landed, so sliding
        # never bunches two substitutions closer than N words apart.
        next_target = ordinal + every

    return tokens, replacements
