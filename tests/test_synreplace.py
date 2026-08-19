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

    def test_add_ed(self):
        cases = {
            "walk": "walked", "like": "liked", "stop": "stopped",
            "carry": "carried", "play": "played", "visit": "visited",
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
        self.assertEqual(self.finder.find("researchers", "NNS"), "investigators")
        self.assertEqual(self.finder.find("difficult", "JJ"), "hard")


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

    def test_empty_input_reports_error(self):
        import io
        from contextlib import redirect_stderr

        from synreplace.cli import main

        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["   "])
        self.assertEqual(code, 1)
        self.assertIn("no input text", err.getvalue())


if __name__ == "__main__":
    unittest.main()
