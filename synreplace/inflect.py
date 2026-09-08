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

# CMU Pronouncing Dictionary, lazily loaded: word -> list of pronunciations,
# each a list of ARPABET phones ("AH0", "K", "ER1", ...). Vowel phones carry a
# trailing stress digit (0 = none, 1 = primary, 2 = secondary); consonants
# don't. Used only to decide whether a CVC-ending word's final syllable is
# stressed -- "occur" (stressed) doubles to "occurred", "open" (unstressed)
# does not double to "openned". Missing/undownloaded data degrades gracefully
# (see `_is_final_syllable_stressed`), so this module still works standalone.
_cmudict = None


def _pronunciations(word: str):
    global _cmudict
    if _cmudict is None:
        try:
            from nltk.corpus import cmudict

            _cmudict = cmudict.dict()
        except LookupError:
            _cmudict = {}
    return _cmudict.get(word, [])


def _is_final_syllable_stressed(word: str):
    """True/False from pronunciation data, or None if `word` isn't in it.

    A single-syllable word's only syllable is trivially "final", so this
    also correctly reports True for e.g. "stop" without any special case.
    Multiple pronunciation variants exist for words like "permit" (noun vs.
    verb stress); any variant with final-syllable primary stress is enough,
    since these functions are only ever applied to a verb's base form.
    """
    pronunciations = _pronunciations(word)
    if not pronunciations:
        return None
    for phones in pronunciations:
        last_vowel = next((p for p in reversed(phones) if p[-1].isdigit()), None)
        if last_vowel is not None and last_vowel[-1] == "1":
            return True
    return False


def _ends_consonant_y(word: str) -> bool:
    """"city" (y -> ies) but not "day" (y -> ys)."""
    return len(word) > 1 and word.endswith("y") and word[-2] not in VOWELS


def _doubles_final_consonant(word: str) -> bool:
    """True for CVC stems whose final syllable is stressed: "stop" -> "stopping",
    "occur" -> "occurring" -- but not "open" -> "openning" or "visit" -> "visitting"."""
    if len(word) < 3:
        return False
    a, b, c = word[-3], word[-2], word[-1]
    if c in VOWELS or c in NO_DOUBLE:
        return False
    if b not in VOWELS:
        return False
    # "qu" is one consonant sound (/kw/), not a vowel digraph, even though
    # 'u' is a vowel letter: "equip"/"quit"/"acquit" are a real CVC shape
    # (kw-i-p, kw-i-t, kw-i-t) and double just like "stop" does.
    is_qu_digraph = a == "u" and len(word) >= 4 and word[-4] == "q"
    if a in VOWELS and not is_qu_digraph:
        return False
    stressed = _is_final_syllable_stressed(word)
    if stressed is not None:
        return stressed
    # No pronunciation data for this word: fall back to the conservative
    # approximation of "single-syllable stems double" (a real stress lookup
    # beats this whenever it's available).
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


def starts_with_vowel_sound(text: str) -> bool:
    """True if `text` is *pronounced* starting with a vowel sound -- "hour"
    (silent h), "individual" -- false for a consonant sound even after a
    vowel letter -- "university", "one" (both start with a /j/ or /w/ glide).
    Decided from pronunciation data when the word has an entry (a vowel
    phone always carries a trailing stress digit, a consonant phone never
    does -- see `_pronunciations`); falls back to the first letter for a
    word cmudict doesn't know. Only the first word of a multi-word
    replacement (`allow_multiword`) matters, e.g. "individual choice".
    """
    word = text.split()[0].lower() if text.split() else text.lower()
    pronunciations = _pronunciations(word)
    if pronunciations:
        first_phone = pronunciations[0][0]
        return first_phone[-1].isdigit()
    return word[:1] in VOWELS


def fix_article(article: str, following_text: str) -> str:
    """Return `article` ("a"/"an", in whatever case) corrected to match
    whether `following_text` now starts with a vowel sound, so a synonym
    swap can't strand "a" in front of a vowel sound or "an" in front of a
    consonant one ("a single discovery" -> "an individual discovery", and
    back). A leading capital carries over via `match_case`; an article that
    was already right comes back unchanged.
    """
    correct = "an" if starts_with_vowel_sound(following_text) else "a"
    return match_case(article, correct)
