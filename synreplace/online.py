"""Synonym sources backed by free, tokenless online dictionary APIs.

Both classes here expose the same interface as `SynonymFinder`
(`find(word, tag)` / `find_top(word, tag, limit)`), so `rewrite_tokens()` can
use any of them interchangeably -- see `SOURCES` in `rewrite.py`.

Trade-off versus the offline WordNet source: these need a live network
connection and one HTTP request per distinct word looked up (cached per
source instance, so a repeated word costs only one request per run), and are
both slower and less predictable than the fully local WordNet path -- a
public API can rate-limit, go down, or change its data at any time.
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from .synonyms import BLOCKED, TAG_MAP, Inflector, eligible_lemma

# Generous on purpose: both APIs are normally fast, but a slow/loaded network
# path can push a single request past several seconds (measured ~20s on one
# such path during development). A short timeout would make the online
# sources silently useless there -- everything would time out and every word
# would just look unreplaceable. Comes at the cost of a genuinely dead/
# unreachable API stalling each lookup for the full timeout before giving up.
REQUEST_TIMEOUT = 10.0  # seconds
USER_AGENT = "synreplace (https://github.com/BartaLazar/LLM-waternark-remover)"


def _get_json(url: str):
    """GET `url` and parse it as JSON, or None on any failure -- network
    error, timeout, non-200 status, bad JSON. A source treats that exactly
    like "no synonyms found for this word", so one flaky request never
    crashes an entire rewrite."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            if response.status != 200:
                return None
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        # OSError covers socket timeouts; ValueError covers JSON decode errors.
        return None


class _WarnOnce:
    """Prints a one-time note to stderr the first time an online source's
    request fails, instead of leaving a user staring at zero substitutions
    with no idea a whole source silently isn't working."""

    def __init__(self) -> None:
        self._warned = False

    def __call__(self, message: str) -> None:
        if not self._warned:
            self._warned = True
            print("synreplace: %s" % message, file=sys.stderr)


def _candidate_ok(normalized: str, lemma: str, allow_multiword: bool) -> bool:
    """Filters shared by both online sources: same rules SynonymFinder
    applies to a WordNet candidate, so a swapped-in API source behaves
    consistently with the offline one."""
    if " " in normalized and not allow_multiword:
        return False
    if normalized in BLOCKED or normalized == lemma:
        return False
    # "quick"/"quickness" style near-duplicates read as typos.
    if normalized.startswith(lemma) or lemma.startswith(normalized):
        return False
    return True


class DatamuseSource:
    """Synonyms from the Datamuse API (https://www.datamuse.com/api/) --
    free, no key or signup, and built specifically for word-relation queries
    (`rel_syn`). `similarity` here is Datamuse's own relevance score,
    normalized against the top result for that particular word -- a
    different *metric* from WordNet's Wu-Palmer score (co-occurrence
    statistics, not graph distance) but the same 0-1 shape, so it displays
    the same way.

    `senses`/`threshold` mean the same thing here as for `SynonymFinder`,
    reinterpreted for a source with no explicit sense groupings of its own:
    `senses` caps how far down Datamuse's own relevance-ranked list we're
    willing to look (its top result is always the "dominant sense" analog),
    and `threshold` drops any candidate whose score, normalized against that
    top result, falls below it.
    """

    # Our internal POS code -> Datamuse's "md=p" part-of-speech tag.
    _DATAMUSE_POS = {"n": "n", "v": "v", "a": "adj", "r": "adv"}

    def __init__(self, senses: int = 3, allow_multiword: bool = False, threshold: float = 0.95) -> None:
        self.senses = max(1, senses)
        self.allow_multiword = allow_multiword
        self.threshold = threshold
        self.inflector = Inflector()
        self._cache: Dict[str, List[Tuple[str, float, Tuple[str, ...]]]] = {}
        self._warn = _WarnOnce()

    def find(self, word: str, tag: str) -> Optional[Tuple[str, float]]:
        results = self.find_top(word, tag, limit=1)
        return results[0] if results else None

    def find_top(self, word: str, tag: str, limit: int = 4) -> List[Tuple[str, float]]:
        mapping = TAG_MAP.get(tag)
        if mapping is None:
            return []
        pos, form = mapping
        lemma = eligible_lemma(word, pos, self.inflector)
        if lemma is None:
            return []

        raw = self._query(lemma)
        if not raw:
            return []
        top_score = raw[0][1] or 1.0  # Datamuse's own top score for this word; the "1.0" anchor

        # POS-filter *before* capping to `senses` -- Datamuse doesn't support
        # filtering server-side the way WordNet's synsets(lemma, pos=pos)
        # does, so doing it in the wrong order here would let an early
        # wrong-POS result crowd out a later correct one, unlike WordNet
        # where the POS filter always happens before the senses-slice.
        wanted_tag = self._DATAMUSE_POS[pos]
        pos_filtered = [item for item in raw if not item[2] or wanted_tag in item[2]]

        scored: List[Tuple[str, float]] = []
        seen_inflected = {word.lower()}
        # Only look as far down Datamuse's own ranking as `senses` allows --
        # same role `synsets[:self.senses]` plays for SynonymFinder.
        for candidate, score, _tags in pos_filtered[: self.senses]:
            similarity = min(1.0, score / top_score)
            if self.threshold > 0 and similarity < self.threshold:
                continue
            normalized = candidate.lower()
            if not _candidate_ok(normalized, lemma, self.allow_multiword):
                continue
            inflected = self.inflector.inflect(normalized, pos, form)
            if inflected is None or inflected in seen_inflected:
                continue
            seen_inflected.add(inflected)
            scored.append((inflected, similarity))
            if len(scored) >= limit:
                break

        return scored

    def _query(self, lemma: str) -> List[Tuple[str, float, Tuple[str, ...]]]:
        """(word, score, pos-tags) for `lemma`, ranked best-first by Datamuse
        itself -- cached so a repeated lemma costs one request per run."""
        if lemma in self._cache:
            return self._cache[lemma]
        url = "https://api.datamuse.com/words?" + urllib.parse.urlencode(
            {"rel_syn": lemma, "md": "p", "max": 20}
        )
        data = _get_json(url)
        if data is None:
            self._warn("Datamuse API request failed or timed out; "
                       "some words may come back with no synonyms.")
            data = []
        parsed = [
            (
                item.get("word", ""),
                item.get("score", 0),
                tuple(t for t in item.get("tags", []) if t in ("n", "v", "adj", "adv")),
            )
            for item in data
        ]
        self._cache[lemma] = parsed
        return parsed


class DictionaryApiSource:
    """Synonyms from the Free Dictionary API (https://dictionaryapi.dev/) --
    free, no key or signup. It's a definitions API with synonyms as a
    secondary field per sense, not a dedicated synonym endpoint, so coverage
    varies a lot by word: some senses list a dozen synonyms, others none at
    all. It reports no relevance score, but its response *is* naturally
    grouped into one entry per meaning of the word, in the order the API
    lists them (its own implicit "most common first" ordering) -- so unlike
    Datamuse, `senses`/`threshold` map onto real structure here rather than
    a stand-in for one: `senses` caps how many of those meaning-entries (for
    the wanted part of speech) are searched, and every candidate from the
    first one scores 1.0 (the "dominant sense") while candidates from any
    later one score `NON_DOMINANT_SIMILARITY` -- a flat marked-down value,
    not a measured relatedness like WordNet's Wu-Palmer score, since this API
    doesn't expose anything to actually measure that with.
    """

    _DICT_POS = {"n": "noun", "v": "verb", "a": "adjective", "r": "adverb"}
    NON_DOMINANT_SIMILARITY = 0.5

    def __init__(self, senses: int = 3, allow_multiword: bool = False, threshold: float = 0.95) -> None:
        self.senses = max(1, senses)
        self.allow_multiword = allow_multiword
        self.threshold = threshold
        self.inflector = Inflector()
        self._cache: Dict[str, List[Tuple[str, List[str]]]] = {}
        self._warn = _WarnOnce()

    def find(self, word: str, tag: str) -> Optional[Tuple[str, float]]:
        results = self.find_top(word, tag, limit=1)
        return results[0] if results else None

    def find_top(self, word: str, tag: str, limit: int = 4) -> List[Tuple[str, float]]:
        mapping = TAG_MAP.get(tag)
        if mapping is None:
            return []
        pos, form = mapping
        lemma = eligible_lemma(word, pos, self.inflector)
        if lemma is None:
            return []

        wanted_pos = self._DICT_POS[pos]
        # Same order as SynonymFinder: filter to the matching part of speech
        # first, *then* cap to `senses` -- so the cap always keeps the K
        # meanings the API considers most relevant to this word, the same
        # way synsets(lemma, pos=pos)[:senses] does for WordNet.
        matching_meanings = [
            synonyms for entry_pos, synonyms in self._query(lemma) if entry_pos == wanted_pos
        ]

        results: List[Tuple[str, float]] = []
        seen_inflected = {word.lower()}
        seen_raw: set = set()
        for meaning_index, synonyms in enumerate(matching_meanings[: self.senses]):
            similarity = 1.0 if meaning_index == 0 else self.NON_DOMINANT_SIMILARITY
            if self.threshold > 0 and similarity < self.threshold:
                continue
            for synonym in synonyms:
                if synonym in seen_raw:
                    continue
                seen_raw.add(synonym)
                normalized = synonym.lower()
                if not _candidate_ok(normalized, lemma, self.allow_multiword):
                    continue
                inflected = self.inflector.inflect(normalized, pos, form)
                if inflected is None or inflected in seen_inflected:
                    continue
                seen_inflected.add(inflected)
                results.append((inflected, similarity))
                if len(results) >= limit:
                    return results
        return results

    def _query(self, lemma: str) -> List[Tuple[str, List[str]]]:
        """(part-of-speech, synonyms) for every meaning of `lemma`, one entry
        per meaning in the API's own order -- cached per lemma (not per part
        of speech) so looking the same lemma up as two different word
        classes still costs one request per run."""
        if lemma in self._cache:
            return self._cache[lemma]
        url = "https://api.dictionaryapi.dev/api/v2/entries/en/" + urllib.parse.quote(lemma)
        data = _get_json(url)
        if data is None:
            self._warn("Free Dictionary API request failed or timed out; "
                       "some words may come back with no synonyms.")
            data = []
        meanings: List[Tuple[str, List[str]]] = []
        for entry in data:
            for meaning in entry.get("meanings", []):
                entry_pos = meaning.get("partOfSpeech", "")
                synonyms = list(meaning.get("synonyms") or [])
                for definition in meaning.get("definitions", []):
                    synonyms.extend(definition.get("synonyms") or [])
                meanings.append((entry_pos, synonyms))
        self._cache[lemma] = meanings
        return meanings
