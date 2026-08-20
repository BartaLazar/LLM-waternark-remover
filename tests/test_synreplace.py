import unittest

from synreplace import rewrite
from synreplace.corpora import ensure_corpora
from synreplace.inflect import add_ed, add_ing, add_s, match_case
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

    def test_match_case(self):
        self.assertEqual(match_case("Dog", "hound"), "Hound")
        self.assertEqual(match_case("DOG", "hound"), "HOUND")
        self.assertEqual(match_case("dog", "hound"), "hound")
        self.assertEqual(match_case("A", "one"), "One")


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


class TestRewrite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_corpora(quiet=True)

    def test_only_targeted_positions_change(self):
        result, replacements = rewrite(SAMPLE, every=3)
        original_words = [t.text for t in tokenize(SAMPLE) if t.is_word]
        result_words = [t.text for t in tokenize(result) if t.is_word]
        self.assertEqual(len(original_words), len(result_words))
        changed = {i for i, (a, b) in enumerate(zip(original_words, result_words), 1) if a != b}
        self.assertEqual(changed, {r.position for r in replacements})
        for position in changed:
            self.assertEqual(position % 3, 0, "changed a word off the N-grid")

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


if __name__ == "__main__":
    unittest.main()
