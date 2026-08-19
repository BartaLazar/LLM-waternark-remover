"""Command-line entry point."""

import argparse
import sys

from . import __version__
from .clipboard import ClipboardError, copy, paste
from .corpora import ensure_corpora
from .rewrite import rewrite

EPILOG = """\
input is taken from, in order of precedence:
  --clip, --input FILE, a TEXT argument, piped stdin, or an interactive
  paste prompt (finish with Ctrl-D, or Ctrl-Z then Enter on Windows)

examples:
  synreplace -n 3 "the quick brown fox jumps over the lazy dog"
  cat draft.md | synreplace -n 5 > rewritten.md
  synreplace -i draft.txt -o rewritten.txt -v
  synreplace --clip -n 4
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synreplace",
        description="Replace every N-th word with its closest WordNet synonym.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("text", nargs="*", help="text to rewrite (optional)")
    parser.add_argument(
        "-n", "--every", type=int, default=5, metavar="N",
        help="replace every N-th word (default: 5)",
    )
    parser.add_argument("-i", "--input", metavar="FILE", help="read text from FILE")
    parser.add_argument("-o", "--output", metavar="FILE", help="write result to FILE")
    parser.add_argument(
        "-c", "--clip", action="store_true",
        help="read from and write back to the system clipboard",
    )
    parser.add_argument(
        "--slide", action="store_true",
        help="if the N-th word has no synonym, try the next word instead",
    )
    parser.add_argument(
        "--senses", type=int, default=1, metavar="K",
        help="consider the K closest word senses, not just the closest (default: 1)",
    )
    parser.add_argument(
        "--multiword", action="store_true",
        help="allow multi-word synonyms such as 'give up'",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="list each substitution on stderr",
    )
    parser.add_argument("--version", action="version", version="synreplace " + __version__)
    return parser


def read_input(args: argparse.Namespace) -> str:
    """Resolve the input source, most explicit first."""
    if args.clip:
        return paste()
    if args.input:
        if args.input == "-":
            return sys.stdin.read()
        with open(args.input, "r", encoding="utf-8") as handle:
            return handle.read()
    if args.text:
        return " ".join(args.text)
    # Not a terminal means something is piped in, so read it without prompting.
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print("Paste your text, then press Ctrl-D to rewrite it:", file=sys.stderr)
    return sys.stdin.read()


def write_output(args: argparse.Namespace, text: str) -> None:
    """Send the result where the flags say. Status messages go to stderr so
    that stdout stays clean for piping."""
    if args.clip:
        copy(text)
        print("Rewritten text copied to clipboard.", file=sys.stderr)
        return
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
        print("Wrote %s" % args.output, file=sys.stderr)
        return
    sys.stdout.write(text)
    # Keep the shell prompt on its own line without altering file/clipboard output.
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.every < 1:
        print("synreplace: -n/--every must be 1 or greater", file=sys.stderr)
        return 2

    try:
        text = read_input(args)
    except (OSError, ClipboardError) as error:
        print("synreplace: %s" % error, file=sys.stderr)
        return 1

    if not text.strip():
        print("synreplace: no input text", file=sys.stderr)
        return 1

    # Deferred until we know there is work to do, so bad flags fail instantly.
    ensure_corpora()
    result, replacements = rewrite(
        text,
        every=args.every,
        senses=args.senses,
        allow_multiword=args.multiword,
        slide=args.slide,
    )

    try:
        write_output(args, result)
    except (OSError, ClipboardError) as error:
        print("synreplace: %s" % error, file=sys.stderr)
        return 1

    if args.verbose:
        for item in replacements:
            print("  #%d %s -> %s" % (item.position, item.original, item.replacement),
                  file=sys.stderr)
        print("%d substitution%s" % (len(replacements), "" if len(replacements) == 1 else "s"),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
