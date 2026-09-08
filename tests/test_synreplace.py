import unittest
from unittest.mock import patch

from synreplace import rewrite, rewrite_tokens
from synreplace.corpora import ensure_corpora
from synreplace.inflect import add_ed, add_ing, add_s, fix_article, match_case, starts_with_vowel_sound
from synreplace.online import DatamuseSource
from synreplace.sources import CompositeSource, SOURCE_NAMES, make_source
from synreplace.synonyms import SynonymFinder
from synreplace.tokens import detokenize, tokenize

SAMPLE = (
    "The quick brown fox jumps over the lazy dog while the researchers "
    "carefully examined the surprising results of their difficult experiment."
)


class TestTokens(unittest.TestCase):
    def test_roundtrip_is_lossless(self):
        for text in [
            SAMPLE,
            "",
            "   ",
            "one\n\ntwo\t three  ",
            "Hyphen-separated, punctuated: don't you think?  ",
            "Numbers 42 and symbols #$% stay put.",
            "Unicode — em dashes, curly ’apostrophes’, café.",
        ]:
            self.assertEqual(detokenize(tokenize(text)), text)

    def test_words_exclude_digits_and_punctuation(self):
        words = [t.text for t in tokenize("ab 12 cd-ef don't") if t.is_word]
        self.assertEqual(words, ["ab", "cd", "ef", "don't"])


class TestInflect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # add_ing/add_ed consult cmudict for stress-aware consonant doubling;
        # make sure it's there before the tests that depend on it run.
        ensure_corpora(quiet=True)

    def test_add_s(self):
        cases = {
            "dog": "dogs", "box": "boxes", "watch": "watches", "bush": "bushes",
            "city": "cities", "day": "days", "potato": "potatoes", "radio": "radios",
        }
        for word, expected in cases.items():
            self.assertEqual(add_s(word), expected, word)

    def test_add_ing(self):
        cases = {
            "walk": "walking", "make": "making", "stop": "stopping",
            "see": "seeing", "lie": "lying", "visit": "visiting", "fix": "fixing",
        }
        for word, expected in cases.items():
            self.assertEqual(add_ing(word), expected, word)

    def test_add_ing_doubles_a_stressed_final_syllable(self):
        # Multi-syllable verbs stressed on their last syllable double it too,
        # not just single-syllable ones ("stop" -> "stopping").
        cases = {
            "occur": "occurring", "prefer": "preferring", "begin": "beginning",
            "admit": "admitting", "permit": "permitting", "refer": "referring",
            "control": "controlling", "regret": "regretting",
        }
        for word, expected in cases.items():
            self.assertEqual(add_ing(word), expected, word)

    def test_add_ing_does_not_double_an_unstressed_final_syllable(self):
        # These end in the same CVC shape but are stressed earlier, so they
        # must not double ("open" -> "opening", not "openning").
        cases = {
            "open": "opening", "listen": "listening", "happen": "happening",
            "benefit": "benefiting", "offer": "offering", "enter": "entering",
            "travel": "traveling",
        }
        for word, expected in cases.items():
            self.assertEqual(add_ing(word), expected, word)

    def test_add_ing_doubles_after_a_qu_digraph(self):
        # "qu" is one consonant sound (/kw/), not a vowel digraph, so these
        # are a real CVC shape and double like any other stressed CVC stem.
        cases = {
            "equip": "equipping", "quit": "quitting", "quiz": "quizzing",
            "acquit": "acquitting",
        }
        for word, expected in cases.items():
            self.assertEqual(add_ing(word), expected, word)

    def test_add_ing_does_not_double_a_real_vowel_digraph(self):
        # Unlike "qu", these really are two vowel sounds/a long vowel, and
        # must not be mistaken for a "qu"-style single consonant unit.
        cases = {
            "rain": "raining", "wait": "waiting", "float": "floating",
            "cheat": "cheating",
        }
        for word, expected in cases.items():
            self.assertEqual(add_ing(word), expected, word)

    def test_add_ed(self):
        cases = {
            "walk": "walked", "like": "liked", "stop": "stopped",
            "carry": "carried", "play": "played", "visit": "visited",
        }
        for word, expected in cases.items():
            self.assertEqual(add_ed(word), expected, word)

    def test_add_ed_doubles_a_stressed_final_syllable(self):
        cases = {
            "occur": "occurred", "prefer": "preferred", "admit": "admitted",
            "permit": "permitted", "refer": "referred", "control": "controlled",
            "regret": "regretted",
        }
        for word, expected in cases.items():
            self.assertEqual(add_ed(word), expected, word)

    def test_add_ed_does_not_double_an_unstressed_final_syllable(self):
        cases = {
            "open": "opened", "listen": "listened", "happen": "happened",
            "benefit": "benefited", "offer": "offered", "enter": "entered",
        }
        for word, expected in cases.items():
            self.assertEqual(add_ed(word), expected, word)

    def test_add_ed_doubles_after_a_qu_digraph(self):
        cases = {
            "equip": "equipped", "quit": "quitted", "quiz": "quizzed",
            "acquit": "acquitted",
        }
        for word, expected in cases.items():
            self.assertEqual(add_ed(word), expected, word)

    def test_match_case(self):
        self.assertEqual(match_case("Dog", "hound"), "Hound")
        self.assertEqual(match_case("DOG", "hound"), "HOUND")
        self.assertEqual(match_case("dog", "hound"), "hound")
        self.assertEqual(match_case("A", "one"), "One")

    def test_starts_with_vowel_sound_uses_pronunciation_not_spelling(self):
        self.assertTrue(starts_with_vowel_sound("hour"))  # silent h
        self.assertTrue(starts_with_vowel_sound("individual"))
        self.assertFalse(starts_with_vowel_sound("university"))  # spelled with u, sounds like "y"
        self.assertFalse(starts_with_vowel_sound("one"))  # sounds like "w"
        self.assertFalse(starts_with_vowel_sound("single"))

    def test_starts_with_vowel_sound_checks_only_the_first_word_of_a_phrase(self):
        self.assertTrue(starts_with_vowel_sound("individual choice"))
        self.assertFalse(starts_with_vowel_sound("single handedly"))

    def test_starts_with_vowel_sound_falls_back_to_spelling_for_unknown_words(self):
        # Not real words, so not in cmudict -- falls back to the first letter.
        self.assertTrue(starts_with_vowel_sound("orblexis"))
        self.assertFalse(starts_with_vowel_sound("zorblex"))

    def test_fix_article_flips_a_and_an_as_needed(self):
        self.assertEqual(fix_article("a", "individual"), "an")
        self.assertEqual(fix_article("an", "single"), "a")

    def test_fix_article_preserves_case(self):
        self.assertEqual(fix_article("A", "individual"), "An")
        self.assertEqual(fix_article("An", "single"), "A")

    def test_fix_article_leaves_an_already_correct_article_unchanged(self):
        self.assertEqual(fix_article("A", "single"), "A")
        self.assertEqual(fix_article("An", "individual"), "An")


class TestSynonymFinder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_corpora(quiet=True)
        cls.finder = SynonymFinder()

    def test_untagged_parts_of_speech_are_left_alone(self):
        for word, tag in [("the", "DT"), ("of", "IN"), ("Paris", "NNP"),
                          ("bigger", "JJR"), ("they", "PRP"), ("42", "CD")]:
            self.assertIsNone(self.finder.find(word, tag), word)

    def test_auxiliaries_are_blocked(self):
        for word, tag in [("is", "VBZ"), ("had", "VBD"), ("being", "VBG")]:
            self.assertIsNone(self.finder.find(word, tag), word)

    def test_irregular_inflections_are_vetoed_not_guessed(self):
        # "go" would become "goed", "foot" would become "foots".
        self.assertIsNone(self.finder._inflect("go", "v", "ed"))
        self.assertIsNone(self.finder._inflect("foot", "n", "s"))
        # Regular ones still work, including a lemma whose past is irregular
        # but whose -s form is not.
        self.assertEqual(self.finder._inflect("walk", "v", "ed"), "walked")
        self.assertEqual(self.finder._inflect("run", "v", "ing"), "running")
        self.assertEqual(self.finder._inflect("dog", "n", "s"), "dogs")

    def test_returns_a_different_word_in_the_same_form(self):
        self.assertEqual(self.finder.find("researchers", "NNS"), ("investigators", 1.0))
        self.assertEqual(self.finder.find("difficult", "JJ"), ("hard", 1.0))

    def test_zero_change_verbs_keep_their_unchanged_past_tense(self):
        # WordNet's own exception files don't cover this verb class (past
        # tense identical to the base form), so the regular guess ("cutted")
        # would otherwise slip through unvetoed. Unlike a normal irregular
        # verb ("go" -> "went", spelling unknown to us), here the correct
        # form is known with certainty: the lemma itself.
        for word in ["cut", "hit", "put", "shut", "hurt", "cost", "set", "burst", "spread"]:
            self.assertEqual(self.finder._inflect(word, "v", "ed"), word)
        # Dialectal cases with a genuine regular alternative are untouched.
        self.assertEqual(self.finder._inflect("quit", "v", "ed"), "quitted")

    def test_multiword_candidates_inflect_the_right_word(self):
        # "set up" + "ed" naively appended gives "set uped". English phrasal
        # verbs put the particle after the verb, so the verb (first word)
        # inflects, not the whole phrase.
        self.assertEqual(self.finder._inflect("set up", "v", "ed"), "set up")
        self.assertEqual(self.finder._inflect("back up", "v", "ed"), "backed up")
        self.assertEqual(self.finder._inflect("back up", "v", "ing"), "backing up")
        # Compound nouns put the head noun last, so that's what pluralizes.
        self.assertEqual(self.finder._inflect("high school", "n", "s"), "high schools")

    def test_find_top_winner_matches_find(self):
        finder = SynonymFinder(senses=3, threshold=0.3)
        for word, tag in [("dog", "NN"), ("difficult", "JJ"), ("researchers", "NNS")]:
            self.assertEqual(finder.find_top(word, tag)[0], finder.find(word, tag))

    def test_find_top_respects_limit_and_excludes_the_winner(self):
        finder = SynonymFinder(senses=3, threshold=0.3)
        results = finder.find_top("difficult", "JJ", limit=2)
        self.assertLessEqual(len(results), 2)
        winner = results[0]
        self.assertNotIn(winner, results[1:])

    def test_find_top_returns_empty_list_not_none_when_nothing_qualifies(self):
        finder = SynonymFinder()
        self.assertEqual(finder.find_top("the", "DT"), [])
        self.assertEqual(finder.find_top("Paris", "NNP"), [])

    def test_default_threshold_is_a_no_op_at_senses_1(self):
        # A word's primary sense is always 100% similar to itself, so the
        # default threshold can never reject anything when senses=1.
        strict = SynonymFinder(senses=1, threshold=0.95)
        permissive = SynonymFinder(senses=1, threshold=0.0)
        for word, tag in [("researchers", "NNS"), ("difficult", "JJ"), ("fox", "NN")]:
            result = strict.find(word, tag)
            self.assertEqual(result, permissive.find(word, tag), word)
            if result is not None:
                self.assertEqual(result[1], 1.0, word)

    def test_high_threshold_rejects_a_distant_sense(self):
        # "fox" (dodger.n.01, wup~0.48) and "lazy" (faineant.s.01, wup~0.5)
        # both have a same-spelling-adjacent candidate only in a weakly
        # related sense reachable via --senses.
        loose = SynonymFinder(senses=3, threshold=0.0)
        strict = SynonymFinder(senses=3, threshold=0.95)
        fox_word, fox_similarity = loose.find("fox", "NN")
        self.assertEqual(fox_word, "dodger")
        self.assertLess(fox_similarity, 0.95)
        self.assertIsNone(strict.find("fox", "NN"))
        lazy_word, lazy_similarity = loose.find("lazy", "JJ")
        self.assertEqual(lazy_word, "indolent")
        self.assertLess(lazy_similarity, 0.95)
        self.assertIsNone(strict.find("lazy", "JJ"))

    def test_threshold_is_ignored_when_disabled(self):
        finder = SynonymFinder(senses=3, threshold=0)
        word, similarity = finder.find("fox", "NN")
        self.assertEqual(word, "dodger")
        self.assertGreater(similarity, 0.0)
        self.assertLess(similarity, 1.0)

    def test_picks_highest_similarity_across_senses_not_first_in_sense_order(self):
        # dog's 2nd sense (frump.n.01, wup~0.60) sorts before its 4th sense
        # (cad.n.01, wup~0.63, lemma "hound") in WordNet's own sense order --
        # the winner should still be whichever scores higher, not whichever
        # sense comes first.
        finder = SynonymFinder(senses=5, threshold=0.5)
        word, similarity = finder.find("dog", "NN")
        self.assertEqual(word, "hound")
        self.assertAlmostEqual(similarity, 0.631578947368421)


class _WordMapFinder:
    """A fake finder that only "knows" a synonym for the exact words given it
    (case-sensitive on purpose -- callers pass the word's own casing), so a
    test can force one specific substitution in a hand-written sentence
    without depending on WordNet's actual choice for that word."""

    def __init__(self, mapping):
        self._mapping = mapping

    def find_top(self, word, tag, limit=4):
        return self._mapping.get(word, [])[:limit]


class TestRewrite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_corpora(quiet=True)

    def test_article_flips_to_an_before_a_vowel_sounding_replacement(self):
        finder = _WordMapFinder({"single": [("individual", 1.0)]})
        result, _ = rewrite("A single discovery matters here today.", every=1, slide=True, finder=finder)
        self.assertEqual(result, "An individual discovery matters here today.")

    def test_article_flips_to_a_before_a_consonant_sounding_replacement(self):
        finder = _WordMapFinder({"individual": [("single", 1.0)]})
        result, _ = rewrite("An individual discovery matters here today.", every=1, slide=True, finder=finder)
        self.assertEqual(result, "A single discovery matters here today.")

    def test_article_fix_uses_pronunciation_not_spelling(self):
        # "university" is spelled with a leading vowel but sounds like "y" --
        # the naive letter-based check would wrongly produce "an university".
        finder = _WordMapFinder({"school": [("university", 1.0)]})
        result, _ = rewrite("A school trip starts soon.", every=1, slide=True, finder=finder)
        self.assertEqual(result, "A university trip starts soon.")
        # "hour" has a silent h, a consonant letter with a vowel sound.
        finder = _WordMapFinder({"meeting": [("hour", 1.0)]})
        result, _ = rewrite("A meeting starts soon.", every=1, slide=True, finder=finder)
        self.assertEqual(result, "An hour starts soon.")

    def test_article_left_alone_when_already_correct(self):
        finder = _WordMapFinder({"quick": [("swift", 1.0)]})
        result, _ = rewrite("A quick fox runs.", every=1, slide=True, finder=finder)
        self.assertEqual(result, "A swift fox runs.")

    def test_article_fix_is_not_recorded_as_its_own_replacement(self):
        finder = _WordMapFinder({"single": [("individual", 1.0)]})
        _, replacements = rewrite("A single discovery matters here today.", every=1, slide=True, finder=finder)
        self.assertEqual([r.original for r in replacements], ["single"])

    def test_article_fix_records_its_own_true_original_on_the_token(self):
        # rewrite_tokens (not rewrite) so the fixed article's *own* prior text
        # is recoverable -- a caller reconstructing "what did this say before"
        # (the web UI's Duplicate view) needs it, since it isn't a Replacement.
        finder = _WordMapFinder({"single": [("individual", 1.0)]})
        tokens, _ = rewrite_tokens("A single discovery matters here today.", every=1, slide=True, finder=finder)
        article_token = next(t for t in tokens if t.is_word and t.text == "An")
        self.assertEqual(article_token.original_text, "A")
        # An untouched word's original_text stays None -- only a token whose
        # text a fix actually changed carries one.
        untouched = next(t for t in tokens if t.is_word and t.text == "discovery")
        self.assertIsNone(untouched.original_text)

    def test_only_targeted_positions_change(self):
        result, replacements = rewrite(SAMPLE, every=4)
        original_words = [t.text for t in tokenize(SAMPLE) if t.is_word]
        result_words = [t.text for t in tokenize(result) if t.is_word]
        self.assertEqual(len(original_words), len(result_words))
        changed = {i for i, (a, b) in enumerate(zip(original_words, result_words), 1) if a != b}
        self.assertEqual(changed, {r.position for r in replacements})
        self.assertTrue(changed, "test input produced no substitutions to check")
        for position in changed:
            # The grid starts at word 1, not word `every`: 1, 1+every, 1+2*every, ...
            self.assertEqual((position - 1) % 4, 0, "changed a word off the N-grid")

    def test_grid_starts_at_the_first_word(self):
        # word 1 is always attempted, regardless of `every` -- not word
        # `every` like a naive "every Nth word, 1-indexed from N" would give.
        result, replacements = rewrite("quick brown fox jumps here", every=5)
        self.assertEqual(result, "speedy brown fox jumps here")
        self.assertEqual([r.position for r in replacements], [1])

    def test_slide_finds_more_substitutions(self):
        _, strict = rewrite(SAMPLE, every=3)
        _, slid = rewrite(SAMPLE, every=3, slide=True)
        self.assertGreater(len(slid), len(strict))

    def test_slide_respects_minimum_spacing(self):
        _, replacements = rewrite(SAMPLE, every=3, slide=True)
        positions = [r.position for r in replacements]
        for earlier, later in zip(positions, positions[1:]):
            self.assertGreaterEqual(later - earlier, 3)

    def test_threshold_narrows_multi_sense_substitutions(self):
        # With senses=3 and the low threshold, "fox" and "lazy" pick up
        # weakly-related synonyms; raising the threshold falls back to
        # skipping/sliding past those two words instead.
        _, loose = rewrite(SAMPLE, every=1, senses=3, threshold=0.0)
        _, strict = rewrite(SAMPLE, every=1, senses=3, threshold=0.95)
        loose_words = {r.original for r in loose}
        strict_words = {r.original for r in strict}
        self.assertIn("fox", loose_words)
        self.assertNotIn("fox", strict_words)

    def test_formatting_is_preserved(self):
        text = "  Line one has words.\n\nLine two: also words!\t(Parenthetical.)\n"
        result, _ = rewrite(text, every=2, slide=True)
        self.assertEqual(
            [t.text for t in tokenize(result) if not t.is_word],
            [t.text for t in tokenize(text) if not t.is_word],
        )

    def test_capitalisation_carries_over(self):
        result, replacements = rewrite("Researchers examined it.", every=1, slide=True)
        self.assertTrue(replacements)
        self.assertTrue(result[0].isupper())

    def test_deterministic(self):
        first, _ = rewrite(SAMPLE, every=2, slide=True)
        second, _ = rewrite(SAMPLE, every=2, slide=True)
        self.assertEqual(first, second)

    def test_texts_without_words(self):
        for text in ["", "   ", "123 !!! ---"]:
            result, replacements = rewrite(text, every=2)
            self.assertEqual(result, text)
            self.assertEqual(replacements, [])

    def test_rejects_invalid_interval(self):
        with self.assertRaises(ValueError):
            rewrite(SAMPLE, every=0)

    def test_rewrite_tokens_reconstructs_the_same_text_as_rewrite(self):
        expected_text, expected_replacements = rewrite(SAMPLE, every=1, slide=True, threshold=0.3)
        tokens, replacements = rewrite_tokens(SAMPLE, every=1, slide=True, threshold=0.3)
        self.assertEqual(detokenize(tokens), expected_text)
        self.assertEqual(
            [(r.position, r.original, r.replacement) for r in replacements],
            [(r.position, r.original, r.replacement) for r in expected_replacements],
        )

    def test_rewrite_tokens_word_tokens_carry_a_matching_position(self):
        tokens, replacements = rewrite_tokens(SAMPLE, every=1, slide=True, threshold=0.3)
        word_tokens = [t for t in tokens if t.is_word]
        self.assertEqual(len(word_tokens), len([t for t in tokenize(SAMPLE) if t.is_word]))
        # Replacement.position is a 1-based ordinal into just the word tokens.
        for replacement in replacements:
            self.assertEqual(word_tokens[replacement.position - 1].text, replacement.replacement)

    def test_replacement_alternatives_are_capped_and_distinct_from_winner(self):
        _, replacements = rewrite_tokens(SAMPLE, every=1, slide=True, senses=3, threshold=0.3)
        seen_any_alternatives = False
        for r in replacements:
            self.assertLessEqual(len(r.alternatives), 3)
            for alt in r.alternatives:
                self.assertNotEqual(alt.word, r.replacement)
                seen_any_alternatives = seen_any_alternatives or True
        self.assertTrue(seen_any_alternatives, "expected at least one word to have alternatives")


class TestCli(unittest.TestCase):
    def test_text_argument_to_stdout(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from synreplace.cli import main

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["-n", "3", "--slide", "-v", SAMPLE])
        self.assertEqual(code, 0)
        self.assertIn("substitution", err.getvalue())
        self.assertTrue(out.getvalue().strip())
        self.assertNotEqual(out.getvalue().strip(), SAMPLE)

    def test_verbose_output_includes_similarity(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from synreplace.cli import main

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["-n", "3", "--slide", "-v", SAMPLE])
        self.assertEqual(code, 0)
        self.assertRegex(err.getvalue(), r"-> \w+ \(\d+% similar\)")

    def test_clipboard_source_is_also_printed(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from unittest.mock import patch

        from synreplace.cli import main

        out, err = io.StringIO(), io.StringIO()
        copied = {}
        with patch("synreplace.cli.paste", return_value=SAMPLE), \
             patch("synreplace.cli.copy", side_effect=lambda text: copied.setdefault("text", text)), \
             redirect_stdout(out), redirect_stderr(err):
            code = main(["--clip", "-n", "3", "--slide"])
        self.assertEqual(code, 0)
        # Went to the clipboard...
        self.assertEqual(copied["text"], out.getvalue().rstrip("\n"))
        # ...and was also echoed to stdout, since there is no other way to see it.
        self.assertTrue(out.getvalue().strip())
        self.assertNotEqual(out.getvalue().strip(), SAMPLE)

    def test_input_file_defaults_to_modified_sibling(self):
        import os
        import tempfile

        from synreplace.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "draft.txt")
            with open(input_path, "w", encoding="utf-8") as handle:
                handle.write(SAMPLE)

            code = main(["-i", input_path, "-n", "3", "--slide"])

            expected_path = os.path.join(tmp, "draft-modified.txt")
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(expected_path))
            with open(expected_path, encoding="utf-8") as handle:
                written = handle.read()
            self.assertNotEqual(written, SAMPLE)

    def test_explicit_output_overrides_default_name(self):
        import os
        import tempfile

        from synreplace.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "draft.txt")
            output_path = os.path.join(tmp, "custom.txt")
            with open(input_path, "w", encoding="utf-8") as handle:
                handle.write(SAMPLE)

            code = main(["-i", input_path, "-o", output_path, "-n", "3", "--slide"])

            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(output_path))
            self.assertFalse(os.path.exists(os.path.join(tmp, "draft-modified.txt")))

    def test_empty_input_reports_error(self):
        import io
        from contextlib import redirect_stderr

        from synreplace.cli import main

        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["   "])
        self.assertEqual(code, 1)
        self.assertIn("no input text", err.getvalue())

    def test_rejects_out_of_range_threshold(self):
        import io
        from contextlib import redirect_stderr

        from synreplace.cli import main

        for bad in ["-0.1", "1.1"]:
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["--threshold", bad, "hello world"])
            self.assertEqual(code, 2)
            self.assertIn("--threshold", err.getvalue())

    def test_threshold_flag_changes_output(self):
        import io
        from contextlib import redirect_stdout

        from synreplace.cli import main

        loose_out, strict_out = io.StringIO(), io.StringIO()
        with redirect_stdout(loose_out):
            main(["-n", "1", "--senses", "3", "--threshold", "0", SAMPLE])
        with redirect_stdout(strict_out):
            main(["-n", "1", "--senses", "3", "--threshold", "0.95", SAMPLE])
        self.assertNotEqual(loose_out.getvalue(), strict_out.getvalue())


# Fixtures captured from real API responses (see synreplace/online.py) so the
# parsing logic is exercised against actual response shapes, without a live
# network call in the test suite itself.
DATAMUSE_HAPPY_ADJ = [
    {"word": "halcyon", "score": 61042, "tags": ["adj"]},
    {"word": "content", "score": 57050, "tags": ["adj", "n", "v"]},
    {"word": "bright", "score": 43054, "tags": ["adj", "n"]},
    {"word": "joyful", "score": 33031, "tags": ["adj"]},
    {"word": "promptly", "score": 30027, "tags": ["adv"]},  # wrong POS, must be filtered out
]

class TestDatamuseSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_corpora(quiet=True)

    def test_returns_candidates_ranked_and_normalized(self):
        # threshold=0 and a wide senses cap isolate ranking/normalization
        # from the (separately tested) threshold- and senses-filtering below.
        with patch("synreplace.online._get_json", return_value=DATAMUSE_HAPPY_ADJ):
            source = DatamuseSource(senses=10, threshold=0)
            results = source.find_top("happy", "JJ", limit=4)
        words = [w for w, _ in results]
        self.assertEqual(words, ["halcyon", "content", "bright", "joyful"])
        self.assertAlmostEqual(results[0][1], 1.0)  # top result always normalizes to 1.0
        self.assertTrue(all(0.0 <= sim <= 1.0 for _, sim in results))
        self.assertEqual(sorted((s for _, s in results), reverse=True), [s for _, s in results])

    def test_threshold_drops_candidates_below_it(self):
        # content=0.93, bright=0.71, joyful=0.54 (normalized) -- only the top
        # result (always 1.0) clears a strict threshold.
        with patch("synreplace.online._get_json", return_value=DATAMUSE_HAPPY_ADJ):
            strict = DatamuseSource(threshold=0.95).find_top("happy", "JJ", limit=4)
            loose = DatamuseSource(threshold=0).find_top("happy", "JJ", limit=4)
        self.assertEqual([w for w, _ in strict], ["halcyon"])
        self.assertGreater(len(loose), len(strict))

    def test_senses_caps_how_far_down_the_ranking_is_searched(self):
        with patch("synreplace.online._get_json", return_value=DATAMUSE_HAPPY_ADJ):
            capped = DatamuseSource(senses=1, threshold=0).find_top("happy", "JJ", limit=4)
            uncapped = DatamuseSource(senses=10, threshold=0).find_top("happy", "JJ", limit=4)
        self.assertEqual([w for w, _ in capped], ["halcyon"])
        self.assertGreater(len(uncapped), len(capped))

    def test_filters_out_wrong_part_of_speech(self):
        with patch("synreplace.online._get_json", return_value=DATAMUSE_HAPPY_ADJ):
            source = DatamuseSource()
            results = source.find_top("happy", "JJ", limit=10)
        self.assertNotIn("promptly", [w for w, _ in results])

    def test_network_failure_yields_empty_list_not_an_exception(self):
        with patch("synreplace.online._get_json", return_value=None):
            source = DatamuseSource()
            self.assertEqual(source.find_top("happy", "JJ"), [])
            self.assertIsNone(source.find("happy", "JJ"))

    def test_repeated_lookup_is_cached(self):
        with patch("synreplace.online._get_json", return_value=DATAMUSE_HAPPY_ADJ) as mock_get:
            source = DatamuseSource()
            source.find_top("happy", "JJ")
            source.find_top("happy", "JJ")
        self.assertEqual(mock_get.call_count, 1)

    def test_untagged_parts_of_speech_are_left_alone(self):
        source = DatamuseSource()
        self.assertEqual(source.find_top("the", "DT"), [])


class _StubSource:
    """A fake synonym source returning a fixed answer, for testing
    CompositeSource's merge/dedupe logic in isolation from any real source.
    Sorts best-first like every real source must -- CompositeSource only
    asks each source for its own top `limit`, trusting that each source's
    own truncation doesn't drop a candidate that would have ranked highly
    overall, so an out-of-order stub isn't a faithful stand-in for one."""

    def __init__(self, results):
        self._results = sorted(results, key=lambda item: -item[1])

    def find_top(self, word, tag, limit=4):
        return self._results[:limit]


class TestCompositeSource(unittest.TestCase):
    def test_merges_candidates_from_every_source(self):
        a = _StubSource([("swift", 0.9), ("rapid", 0.6)])
        b = _StubSource([("speedy", 0.8)])
        combo = CompositeSource([a, b])
        words = {w for w, _ in combo.find_top("quick", "JJ", limit=10)}
        self.assertEqual(words, {"swift", "rapid", "speedy"})

    def test_a_candidate_from_two_sources_keeps_the_higher_score(self):
        a = _StubSource([("swift", 0.4)])
        b = _StubSource([("swift", 0.9)])
        combo = CompositeSource([a, b])
        results = dict(combo.find_top("quick", "JJ", limit=10))
        self.assertEqual(results["swift"], 0.9)

    def test_results_are_ranked_by_score_descending(self):
        a = _StubSource([("low", 0.2), ("high", 0.9)])
        combo = CompositeSource([a])
        words = [w for w, _ in combo.find_top("quick", "JJ", limit=10)]
        self.assertEqual(words, ["high", "low"])

    def test_respects_the_overall_limit_after_merging(self):
        a = _StubSource([("a1", 0.9), ("a2", 0.8), ("a3", 0.7)])
        b = _StubSource([("b1", 0.95)])
        combo = CompositeSource([a, b])
        results = combo.find_top("quick", "JJ", limit=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "b1")

    def test_requires_at_least_one_source(self):
        with self.assertRaises(ValueError):
            CompositeSource([])

    def test_find_returns_the_single_best_candidate(self):
        combo = CompositeSource([_StubSource([("swift", 0.4), ("rapid", 0.9)])])
        self.assertEqual(combo.find("quick", "JJ"), ("rapid", 0.9))


class TestMakeSource(unittest.TestCase):
    def test_single_name_returns_that_source_directly_not_wrapped(self):
        source = make_source(["wordnet"])
        self.assertIsInstance(source, SynonymFinder)

    def test_multiple_names_returns_a_composite(self):
        source = make_source(["wordnet", "datamuse"])
        self.assertIsInstance(source, CompositeSource)
        self.assertEqual(len(source.sources), 2)

    def test_duplicate_names_are_deduplicated(self):
        source = make_source(["wordnet", "wordnet"])
        self.assertIsInstance(source, SynonymFinder)  # not a Composite of two identical sources

    def test_rejects_unknown_source_names(self):
        with self.assertRaises(ValueError):
            make_source(["not-a-real-source"])

    def test_rejects_empty_source_list(self):
        with self.assertRaises(ValueError):
            make_source([])

    def test_every_declared_source_name_is_buildable(self):
        for name in SOURCE_NAMES:
            make_source([name])  # must not raise


class TestSourcesCli(unittest.TestCase):
    def test_build_parser_accepts_comma_separated_sources(self):
        from synreplace.cli import build_parser

        args = build_parser().parse_args(["--sources", "wordnet,datamuse", "hello"])
        self.assertEqual(args.sources, ["wordnet", "datamuse"])

    def test_default_sources_is_wordnet_only(self):
        from synreplace.cli import build_parser

        args = build_parser().parse_args(["hello"])
        self.assertEqual(args.sources, ["wordnet"])

    def test_unknown_source_name_is_rejected_with_exit_code_2(self):
        import io
        from contextlib import redirect_stderr

        from synreplace.cli import main

        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                main(["--sources", "not-a-real-source", "hello world"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("unknown source", err.getvalue())


if __name__ == "__main__":
    unittest.main()
