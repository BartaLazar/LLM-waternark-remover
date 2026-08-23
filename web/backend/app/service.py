"""Thin wrapper around the synreplace library.

Kept separate from main.py so the HTTP layer (FastAPI request/response
handling) stays independent of the actual text-processing logic, and so a
SynonymFinder -- which does real work building its irregular-verb lookup
tables -- is reused across requests that share the same parameters instead of
rebuilt from scratch every time.
"""

from functools import lru_cache
from typing import List, Tuple

from synreplace.rewrite import Replacement, rewrite_tokens
from synreplace.synonyms import SynonymFinder
from synreplace.tokens import Token


@lru_cache(maxsize=64)
def _get_finder(senses: int, threshold: float, allow_multiword: bool) -> SynonymFinder:
    return SynonymFinder(senses=senses, allow_multiword=allow_multiword, threshold=threshold)


def process_rewrite(
    text: str,
    every: int,
    slide: bool,
    senses: int,
    threshold: float,
    allow_multiword: bool,
) -> Tuple[List[Token], List[Replacement]]:
    """Returns the full token list (not just the joined string) so the API
    layer can also hand the client per-word editing support -- see
    schemas.TextToken."""
    finder = _get_finder(senses, threshold, allow_multiword)
    return rewrite_tokens(text, every=every, slide=slide, finder=finder)
