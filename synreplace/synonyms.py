"""Closest-synonym lookup backed by WordNet."""

from typing import Dict, List, Optional, Sequence, Set, Tuple

from .inflect import add_ed, add_ing, add_s

# Penn Treebank tag -> (WordNet POS, surface form to reproduce).
# Tags absent from this table are never replaced: determiners, pronouns,
# prepositions, conjunctions, numbers and proper nouns (NNP/NNPS) all stay put,
# and so do comparatives/superlatives (JJR/RBR/...), whose synonyms cannot be
# re-inflected reliably.
TAG_MAP: Dict[str, Tuple[str, str]] = {
    "NN": ("n", "base"),
    "NNS": ("n", "s"),
    "VB": ("v", "base"),
    "VBP": ("v", "base"),
    "VBZ": ("v", "s"),
    "VBG": ("v", "ing"),
    "VBD": ("v", "ed"),
    "VBN": ("v", "ed"),
    "JJ": ("a", "base"),
    "RB": ("r", "base"),
}

# Auxiliaries and light verbs the tagger reports as ordinary verbs. Swapping
# these mangles the sentence far more often than it varies it.
BLOCKED = frozenset(
    """
    be am is are was were been being have has had do does did
    will would shall should may might must can could
    let get got go went gone come came make made take took
    thing things way ways
    """.split()
)

MIN_LENGTH = 3


class SynonymFinder:
    """Finds a drop-in synonym for a tagged word, or None when there is none.

    "Closest" means: among the `senses` most common meanings of the word,
    whichever candidate is most similar (Wu-Palmer score) to its single most
    common meaning; ties broken by corpus frequency, then alphabetically.
    At the default `senses=1` this collapses to "the most frequent lemma in
    the word's single most common sense."

    `threshold` gates how far `senses` is allowed to stray from that primary
    sense. A word's own synset is always 100% similar to itself, so with the
    default `senses=1` every candidate already meets any threshold trivially;
    the threshold only starts rejecting candidates once `senses > 1` opens up
    less-related meanings of the word.
    """

    def __init__(
        self, senses: int = 1, allow_multiword: bool = False, threshold: float = 0.95
    ) -> None:
        self.senses = max(1, senses)
        self.allow_multiword = allow_multiword
        self.threshold = threshold
        self._wn = None
        self._irregulars: Dict[str, Dict[str, Set[str]]] = {}

    @property
    def wn(self):
        """WordNet, loaded on first use so `--help` stays instant."""
        if self._wn is None:
            from nltk.corpus import wordnet

            wordnet.ensure_loaded()
            self._wn = wordnet
        return self._wn

    def find(self, word: str, tag: str) -> Optional[Tuple[str, float]]:
        """Best (synonym, similarity) for `word` in the same form, or None.

        `similarity` is the candidate's Wu-Palmer score against the word's
        dominant sense -- see `_candidates`. It is always `1.0` unless
        `senses > 1` pulled the winning candidate from a less common sense.
        """
        mapping = TAG_MAP.get(tag)
        if mapping is None:
            return None  # part of speech we never touch
        pos, form = mapping

        lowered = word.lower()
        # Contractions ("don't") have no clean lemma, and very short words are
        # almost all function words.
        if len(lowered) < MIN_LENGTH or lowered in BLOCKED or "'" in lowered or "’" in lowered:
            return None

        # morphy strips inflection: "researchers" -> "researcher".
        lemma = self.wn.morphy(lowered, pos) or lowered
        if lemma in BLOCKED:
            return None

        # Walk candidates best-first and take the first one we can inflect
        # correctly; a candidate that only differs by inflection is no change.
        for candidate, similarity in self._candidates(lemma, pos):
            inflected = self._inflect(candidate, pos, form)
            if inflected is not None and inflected != lowered:
                return inflected, similarity
        return None

    def _candidates(self, lemma: str, pos: str) -> List[Tuple[str, float]]:
        """(lemma, similarity) candidates, most similar sense first, most
        frequent first within a similarity tier.

        `similarity` is each candidate's Wu-Palmer score (WordNet's standard
        0-1 relatedness measure, based on how close two senses' nearest shared
        ancestor is in the meaning hierarchy) against the word's own dominant
        sense. The dominant sense is always `1.0` similar to itself; senses
        with no comparable path score `0.0`. Below `threshold`, a sense is
        dropped entirely rather than reported with a low score.
        """
        # WordNet returns synsets ordered by how common the sense is, so
        # slicing to `senses` keeps us near the word's dominant meaning.
        synsets = self.wn.synsets(lemma, pos=pos)[: self.senses]
        if not synsets:
            return []
        primary_sense = synsets[0]  # what "similarity" is measured against

        # Collect every qualifying candidate first, then rank globally --
        # rather than sense by sense -- so the closest-meaning synonym wins
        # even if it happens to sit in the word's 2nd or 3rd most common sense.
        scored: List[Tuple[float, int, str]] = []
        seen: Set[str] = {lemma}
        for synset in synsets:
            if synset is primary_sense:
                similarity = 1.0
            else:
                similarity = synset.wup_similarity(primary_sense) or 0.0
                if self.threshold > 0 and similarity < self.threshold:
                    continue  # this whole sense drifted too far from the dominant one
            for wn_lemma in synset.lemmas():
                name = wn_lemma.name()
                if "_" in name or "-" in name:
                    if not self.allow_multiword:
                        continue
                    name = name.replace("_", " ").replace("-", " ")
                normalized = name.lower()
                if normalized in seen or normalized in BLOCKED:
                    continue
                # "quick"/"quickness" style near-duplicates read as typos.
                if normalized.startswith(lemma) or lemma.startswith(normalized):
                    continue
                seen.add(normalized)
                scored.append((similarity, wn_lemma.count(), normalized))

        # Highest similarity first; within a tie, highest frequency; within
        # that, alphabetical, so the same input always gives the same output.
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [(name, similarity) for similarity, _, name in scored]

    def _inflect(self, lemma: str, pos: str, form: str) -> Optional[str]:
        """Reproduce `form` for `lemma`, or None if only an irregular would do."""
        if form == "base":
            return lemma
        if form == "s":
            regular = add_s(lemma)
        elif form == "ing":
            regular = add_ing(lemma)
        else:
            regular = add_ed(lemma)

        known = self._irregular_forms(pos, lemma, form)
        if known and regular not in known:
            # WordNet says this lemma inflects irregularly here ("go" -> "went"),
            # and the regular guess would be wrong. Skip the candidate.
            return None
        return regular

    def _irregular_forms(self, pos: str, lemma: str, form: str) -> Sequence[str]:
        """The lemma's known irregular spellings *for this form only*.

        Verb exception lists mix all the forms together ("run" -> "ran", "abet"
        -> "abetting"), so they are filtered by suffix shape. Without that,
        "ran" would wrongly veto the perfectly regular "runs".
        """
        forms = self._reverse_exceptions(pos).get(lemma)
        if not forms:
            return ()
        if pos == "n":
            # Noun exceptions are exclusively irregular plurals.
            return tuple(forms)
        if form == "ing":
            return tuple(f for f in forms if f.endswith("ing"))
        if form == "s":
            return tuple(f for f in forms if f.endswith("s") and not f.endswith("ing"))
        # Past tense / participle: whatever is left over.
        return tuple(f for f in forms if not f.endswith("ing") and not f.endswith("s"))

    def _reverse_exceptions(self, pos: str) -> Dict[str, Set[str]]:
        """lemma -> irregular surface forms, inverted from WordNet's .exc files."""
        if pos not in self._irregulars:
            reverse: Dict[str, Set[str]] = {}
            table = getattr(self.wn, "_exception_map", {}).get(pos, {})
            for surface, lemmas in table.items():
                for lemma in lemmas:
                    reverse.setdefault(lemma, set()).add(surface)
            self._irregulars[pos] = reverse
        return self._irregulars[pos]
