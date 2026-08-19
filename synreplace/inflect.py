"""Rule-based English inflection, plus case matching.

WordNet stores lemmas ("dog", "run"), but the word being replaced is usually
inflected ("dogs", "running"). These helpers put a candidate lemma back into
the same shape as the word it replaces. The rules cover regular morphology
only -- irregular forms are detected and vetoed in `synonyms.py` rather than
guessed at here.
"""

VOWELS = "aeiou"
# Consonants that are not doubled before a suffix, even after a stressed CVC.
NO_DOUBLE = "hwxy"
SIBILANT_ENDINGS = ("s", "x", "z", "ch", "sh")


def _ends_consonant_y(word: str) -> bool:
    """"city" (y -> ies) but not "day" (y -> ys)."""
    return len(word) > 1 and word.endswith("y") and word[-2] not in VOWELS


def _doubles_final_consonant(word: str) -> bool:
    """True for short CVC stems like "stop" -> "stopping"."""
    if len(word) < 3:
        return False
    a, b, c = word[-3], word[-2], word[-1]
    if c in VOWELS or c in NO_DOUBLE:
        return False
    if b not in VOWELS or a in VOWELS:
        return False
    # Only single-syllable-ish stems double; "visit" -> "visiting", not
    # "visitting". Approximated by counting vowel groups.
    return _vowel_groups(word) == 1


def _vowel_groups(word: str) -> int:
    """Rough syllable count: runs of adjacent vowels, e.g. "visit" -> 2."""
    groups = 0
    previous_was_vowel = False
    for char in word:
        is_vowel = char in VOWELS
        if is_vowel and not previous_was_vowel:
            groups += 1
        previous_was_vowel = is_vowel
    return groups


def add_s(word: str) -> str:
    """Noun plural and 3rd-person-singular verb share one rule set."""
    if word.endswith(SIBILANT_ENDINGS):
        return word + "es"  # box -> boxes, watch -> watches
    if _ends_consonant_y(word):
        return word[:-1] + "ies"  # city -> cities
    if word.endswith("o") and len(word) > 1 and word[-2] not in VOWELS:
        return word + "es"  # potato -> potatoes, but radio -> radios
    return word + "s"


def add_ing(word: str) -> str:
    if word.endswith("ie"):
        return word[:-2] + "ying"  # lie -> lying
    if word.endswith("e") and not word.endswith(("ee", "oe", "ye")):
        return word[:-1] + "ing"  # make -> making, but see -> seeing
    if _doubles_final_consonant(word):
        return word + word[-1] + "ing"  # stop -> stopping
    return word + "ing"


def add_ed(word: str) -> str:
    if word.endswith("e"):
        return word + "d"  # like -> liked
    if _ends_consonant_y(word):
        return word[:-1] + "ied"  # carry -> carried
    if _doubles_final_consonant(word):
        return word + word[-1] + "ed"  # stop -> stopped
    return word + "ed"


def match_case(original: str, replacement: str) -> str:
    """Carry the original word's capitalisation over to its replacement."""
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement
