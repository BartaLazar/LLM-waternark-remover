"""Lossless tokenizer: split text into words and the gaps between them.

Joining every token's text back together reproduces the input byte for byte,
so punctuation, newlines and odd spacing survive a rewrite untouched.
"""

import re
from dataclasses import dataclass
from typing import List

# A word is letters, optionally joined by straight or curly apostrophes
# ("don't", "rock'n'roll"). Digits and punctuation fall into the gaps.
WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*")


@dataclass
class Token:
    text: str
    is_word: bool  # False for the whitespace/punctuation runs between words


def tokenize(text: str) -> List[Token]:
    """Split `text` into alternating gap and word tokens, losing nothing."""
    tokens: List[Token] = []
    pos = 0  # end of the last token emitted
    for match in WORD_RE.finditer(text):
        # Everything skipped over since the previous word is one gap token.
        if match.start() > pos:
            tokens.append(Token(text[pos : match.start()], False))
        tokens.append(Token(match.group(), True))
        pos = match.end()
    # Trailing punctuation or newline after the final word.
    if pos < len(text):
        tokens.append(Token(text[pos:], False))
    return tokens


def detokenize(tokens: List[Token]) -> str:
    """Inverse of `tokenize`: gaps carry the original spacing, so a plain join works."""
    return "".join(token.text for token in tokens)
