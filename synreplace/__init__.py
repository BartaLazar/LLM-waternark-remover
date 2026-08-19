"""Replace every N-th word in a text with its closest WordNet synonym."""

__version__ = "0.1.0"

from .rewrite import Replacement, rewrite

__all__ = ["Replacement", "rewrite", "__version__"]
