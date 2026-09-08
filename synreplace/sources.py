"""Picks and combines synonym sources.

A "source" is any object exposing `find(word, tag)` / `find_top(word, tag,
limit)` -- `SynonymFinder` (offline WordNet), `DatamuseSource`, and
`DictionaryApiSource` (both online) all satisfy this. One or more source
*names* are resolved to source objects here, and combined into one via
`CompositeSource` when more than one is requested.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from .online import DatamuseSource, DictionaryApiSource
from .synonyms import SynonymFinder

# Every valid source name, and what each one actually is -- shown to users
# (CLI --help, the web API's /info, the web UI's source picker) so this is
# the one place that needs updating to add another source later.
SOURCE_NAMES: Tuple[str, ...] = ("wordnet", "datamuse", "dictionaryapi")

SOURCE_DESCRIPTIONS: Dict[str, str] = {
    "wordnet": "Standard dictionary (WordNet, offline, no network needed)",
    "datamuse": "Datamuse API (online, no key needed)",
    "dictionaryapi": "Free Dictionary API (online, no key needed)",
}

DEFAULT_SOURCES: Tuple[str, ...] = ("wordnet",)


class CompositeSource:
    """Queries every given source for the same word and merges their
    candidates into one ranked pool, so enabling more than one source
    broadens the pool instead of picking exactly one to use.

    A candidate found by more than one source keeps the highest score any of
    them gave it. Similarity scores come from different metrics per source
    (WordNet's graph-distance score vs. an API's relevance score, or a fixed
    value from a source with no ranking of its own) but are all normalized
    to the same 0-1 range already, so ranking the merged pool by score is
    still meaningful even though the metrics aren't identical.
    """

    def __init__(self, sources: Sequence[object]) -> None:
        if not sources:
            raise ValueError("CompositeSource needs at least one source")
        self.sources = list(sources)

    def find(self, word: str, tag: str) -> Optional[Tuple[str, float]]:
        results = self.find_top(word, tag, limit=1)
        return results[0] if results else None

    def find_top(self, word: str, tag: str, limit: int = 4) -> List[Tuple[str, float]]:
        best: Dict[str, float] = {}
        for source in self.sources:
            for candidate, score in source.find_top(word, tag, limit=limit):
                if candidate not in best or score > best[candidate]:
                    best[candidate] = score
        # Highest score first; alphabetical tiebreak so results stay
        # deterministic even when two sources hand back the same score.
        ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:limit]


def make_source(
    names: Sequence[str],
    senses: int = 3,
    allow_multiword: bool = False,
    threshold: float = 0.95,
) -> object:
    """Builds the source (or `CompositeSource` of several) for `names`.

    `senses`/`threshold` apply to every source, not just `wordnet` -- each
    online source reinterprets them for its own shape of data (see
    `DatamuseSource`/`DictionaryApiSource`'s docstrings for what "sense" and
    "similarity" mean for that particular one), rather than ignoring them.
    """
    names = list(dict.fromkeys(names))  # de-duplicate, keep first-seen order
    if not names:
        raise ValueError("at least one source is required")
    unknown = [name for name in names if name not in SOURCE_NAMES]
    if unknown:
        raise ValueError(
            "unknown source(s): %s (choose from %s)" % (", ".join(unknown), ", ".join(SOURCE_NAMES))
        )

    built = []
    for name in names:
        if name == "wordnet":
            built.append(SynonymFinder(senses=senses, allow_multiword=allow_multiword, threshold=threshold))
        elif name == "datamuse":
            built.append(DatamuseSource(senses=senses, allow_multiword=allow_multiword, threshold=threshold))
        else:  # "dictionaryapi"
            built.append(DictionaryApiSource(senses=senses, allow_multiword=allow_multiword, threshold=threshold))

    return built[0] if len(built) == 1 else CompositeSource(built)
