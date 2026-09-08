"""Replace every N-th word in a text with its closest synonym."""

__version__ = "0.1.0"

from .rewrite import Alternative, Replacement, rewrite, rewrite_tokens
from .sources import SOURCE_DESCRIPTIONS, SOURCE_NAMES, make_source

__all__ = [
    "Alternative", "Replacement", "rewrite", "rewrite_tokens",
    "SOURCE_NAMES", "SOURCE_DESCRIPTIONS", "make_source", "__version__",
]
