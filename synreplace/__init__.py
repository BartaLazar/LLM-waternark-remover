"""Replace every N-th word in a text with its closest WordNet synonym."""

__version__ = "0.1.0"

from .rewrite import Alternative, Replacement, rewrite, rewrite_tokens

__all__ = ["Alternative", "Replacement", "rewrite", "rewrite_tokens", "__version__"]
