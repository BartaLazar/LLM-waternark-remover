"""Closest-synonym lookup backed by WordNet."""

from typing import Dict, List, Optional, Sequence, Set, Tuple

from .inflect import add_ed, add_ing, add_s

# Penn Treebank tag -> (WordNet POS, surface form to reproduce).
# Tags absent from this table are never replaced: determiners, pronouns,
# prepositions, conjunctions, numbers and proper nouns (NNP/NNPS) all stay put,
# and so do comparatives/superlatives (JJR/RBR/...), whose synonyms cannot be
# re-inflected reliably.
#
# Shared by every synonym source (WordNet or an online dictionary API) --
# which words are even eligible for replacement, and in what grammatical
# form a candidate needs to come back, doesn't depend on where the candidate
# itself was found.
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

# Verbs whose past tense/participle is identical to the base form ("cut",
# never "cutted"). WordNet's own morphological exception files don't cover
# this class at all -- they only list forms that *differ* from the base, and
# these don't -- so left alone the regular guess (add_ed) slips through
# unvetoed. Dialectal cases with a genuinely regular alternative in some
# variety of English ("quit"/"quitted", "fit"/"fitted", "knit"/"knitted",
# "wed"/"wedded") are deliberately left out so that guess isn't overridden.
ZERO_CHANGE_VERBS = frozenset(
    """
    bet bid broadcast burst cast cost cut hit hurt put rid set shed shut
    slit spread sublet thrust upset offset forecast recast preset
    rebroadcast outbid
    """.split()
)


class Inflector:
    """WordNet-backed lemmatization and re-inflection.

    Shared by every synonym source -- offline WordNet lookup or an online
    dictionary API -- so a candidate comes back in the same grammatical form
    as the word it's replacing no matter where it was found. WordNet's
    morphological data (used here) is a different thing from its synonym
    data (used only by `SynonymFinder`): reusing the former for an API-backed
    source isn't a compromise on "using an API for synonyms", it's just
    correct, free spell-shape knowledge that no dictionary API bothers to
    expose on its own.
    """

    def __init__(self) -> None:
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

    def lemmatize(self, word: str, pos: str) -> str:
        """Strip inflection: "researchers" -> "researcher"."""
        return self.wn.morphy(word, pos) or word

    def inflect(self, lemma: str, pos: str, form: str) -> Optional[str]:
        """Reproduce `form` for `lemma`, or None if only an irregular would do."""
        if form == "base":
            return lemma
        if " " in lemma:
            # Multi-word candidates (only possible with allow_multiword) need
            # the suffix on the right word, not tacked onto the whole phrase:
            # "set up" -> "set up" + "ed" would give "set uped". English
            # phrasal verbs put the particle after the verb ("set up",
            # "back off"), so the verb -- the first word -- is the one that
            # inflects; compound nouns put the head noun last ("high school"
            # -> "high schools"), so that's the last word instead.
            if pos == "v":
                head, sep, rest = lemma.partition(" ")
                inflected_head = self._inflect_word(head, pos, form)
                return None if inflected_head is None else inflected_head + sep + rest
            if pos == "n":
                rest, sep, tail = lemma.rpartition(" ")
                inflected_tail = self._inflect_word(tail, pos, form)
                return None if inflected_tail is None else rest + sep + inflected_tail
        return self._inflect_word(lemma, pos, form)

    def _inflect_word(self, lemma: str, pos: str, form: str) -> Optional[str]:
        """Reproduce `form` for a single word, or None if only an irregular would do."""
        if pos == "v" and form == "ed" and lemma in ZERO_CHANGE_VERBS:
            # Unlike an ordinary irregular verb ("go" -> "went", spelling
            # unknown to us), a zero-change verb's past tense is *known* --
            # it's the lemma itself -- so return it instead of vetoing a
            # perfectly good candidate for no reason.
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


def eligible_lemma(word: str, pos: str, inflector: Inflector) -> Optional[str]:
    """The lemma to look up for `word`, or None if it's not worth trying at
    all (too short, a contraction, a blocked function word). Shared by every
    synonym source as the first filtering step before it spends a lookup --
    local or over the network -- on a word that was never going to qualify."""
    lowered = word.lower()
    if len(lowered) < MIN_LENGTH or lowered in BLOCKED or "'" in lowered or "’" in lowered:
        return None
    lemma = inflector.lemmatize(lowered, pos)
    if lemma in BLOCKED:
        return None
    return lemma


class SynonymFinder:
    """Finds a drop-in synonym for a tagged word, or None when there is none.

    "Closest" means: among the `senses` most common meanings of the word,
    whichever candidate is most similar (Wu-Palmer score) to its single most
    common meaning; ties broken by corpus frequency, then alphabetically.
    At `senses=1` this collapses to "the most frequent lemma in the word's
    single most common sense."

    `threshold` gates how far `senses` is allowed to stray from that primary
    sense. A word's own synset is always 100% similar to itself, so at
    `senses=1` every candidate already meets any threshold trivially; the
    threshold only starts rejecting candidates once `senses > 1` opens up
    less-related meanings of the word -- which is the default (`senses=3`),
    so `threshold` is doing real filtering work out of the box.
    """

    def __init__(
        self, senses: int = 3, allow_multiword: bool = False, threshold: float = 0.95
    ) -> None:
        self.senses = max(1, senses)
        self.allow_multiword = allow_multiword
        self.threshold = threshold
        self.inflector = Inflector()

    @property
    def wn(self):
        return self.inflector.wn

    def find(self, word: str, tag: str) -> Optional[Tuple[str, float]]:
        """Best (synonym, similarity) for `word` in the same form, or None.

        `similarity` is the candidate's Wu-Palmer score against the word's
        dominant sense -- see `_candidates`. It is always `1.0` unless
        `senses > 1` pulled the winning candidate from a less common sense.
        """
        results = self.find_top(word, tag, limit=1)
        return results[0] if results else None

    def find_top(self, word: str, tag: str, limit: int = 4) -> List[Tuple[str, float]]:
        """Up to `limit` valid (synonym, similarity) candidates for `word`,
        best first -- `find()`'s winner is always `find_top(...)[0]`. The
        rest are usable as alternative choices (e.g. for a UI picker)."""
        mapping = TAG_MAP.get(tag)
        if mapping is None:
            return []  # part of speech we never touch
        pos, form = mapping

        lemma = eligible_lemma(word, pos, self.inflector)
        if lemma is None:
            return []

        # Walk candidates best-first, keeping every one that inflects to a
        # form actually different from the original, until `limit` is hit.
        results: List[Tuple[str, float]] = []
        seen_inflected = {word.lower()}
        for candidate, similarity in self._candidates(lemma, pos):
            inflected = self.inflector.inflect(candidate, pos, form)
            if inflected is None or inflected in seen_inflected:
                continue
            seen_inflected.add(inflected)
            results.append((inflected, similarity))
            if len(results) >= limit:
                break
        return results

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
        """Deprecated alias for `self.inflector.inflect` -- kept so existing
        callers (including tests) that reach into this "private" method
        directly don't break."""
        return self.inflector.inflect(lemma, pos, form)
