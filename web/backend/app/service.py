"""Thin wrapper around the synreplace library.

Kept separate from main.py so the HTTP layer (FastAPI request/response
handling) stays independent of the actual text-processing logic, and so a
source -- which does real work building its irregular-verb lookup tables, or
caching per-word results from an online API -- is reused across requests
that share the same parameters instead of rebuilt from scratch every time.
Note the online sources' per-word cache then grows for as long as the server
process lives; fine for a personal/demo deployment, but an eviction policy
would be worth adding before this ran under sustained real traffic.
"""

from functools import lru_cache
from typing import List, Sequence, Tuple

from synreplace.rewrite import Replacement, rewrite_tokens
from synreplace.sources import make_source
from synreplace.tokens import Token


@lru_cache(maxsize=64)
def _get_source(sources: Tuple[str, ...], senses: int, threshold: float, allow_multiword: bool):
    return make_source(sources, senses=senses, allow_multiword=allow_multiword, threshold=threshold)


def process_rewrite(
    text: str,
    every: int,
    slide: bool,
    senses: int,
    threshold: float,
    allow_multiword: bool,
    sources: Sequence[str],
) -> Tuple[List[Token], List[Replacement]]:
    """Returns the full token list (not just the joined string) so the API
    layer can also hand the client per-word editing support -- see
    schemas.TextToken."""
    # Sorted before caching: {"wordnet","datamuse"} and {"datamuse","wordnet"}
    # produce the same merged pool, so they should share one cached source
    # rather than each building (and separately caching results for) its own.
    source = _get_source(tuple(sorted(sources)), senses, threshold, allow_multiword)
    return rewrite_tokens(text, every=every, slide=slide, finder=source)
