"""Command-line entry point."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .clipboard import ClipboardError, copy, paste
from .corpora import ensure_corpora
from .rewrite import rewrite
from .sources import DEFAULT_SOURCES, SOURCE_DESCRIPTIONS, SOURCE_NAMES

EPILOG = """\
input is taken from, in order of precedence:
  --clip, --input FILE, a TEXT argument, piped stdin, or an interactive
  paste prompt (finish with Ctrl-D, or Ctrl-Z then Enter on Windows)

--input FILE without --output writes to FILE-modified next to FILE, rather
than to stdout.

sources (--sources NAME[,NAME...], default: wordnet):
%s

  Naming more than one pools their candidates together rather than picking
  one -- e.g. --sources wordnet,datamuse considers both. The online sources
  need a network connection and are slower and less predictable than the
  offline default. --senses/--threshold apply to every enabled source, not
  just wordnet -- see README.md for what they mean for each one.

examples:
  synreplace -n 3 "the quick brown fox jumps over the lazy dog"
  cat draft.md | synreplace -n 5 > rewritten.md
  synreplace -i draft.txt -v          # writes draft-modified.txt
  synreplace -i draft.txt -o out.txt -v
  synreplace --clip -n 4
  synreplace --senses 3 --threshold 0.8 -v "the quick brown fox jumps"
  synreplace --sources wordnet,datamuse -v "the quick brown fox jumps"
""" % "\n".join("  %-14s %s" % (name, SOURCE_DESCRIPTIONS[name]) for name in SOURCE_NAMES)


def default_output_path(input_path: str) -> str:
    """FILE -> FILE-modified next to it, e.g. draft.txt -> draft-modified.txt."""
    path = Path(input_path)
    return str(path.with_name(path.stem + "-modified" + path.suffix))


def source_list(value: str):
    """argparse type for --sources: a comma-separated list of source names,
    validated against SOURCE_NAMES so a typo fails fast with a clear message
    rather than surfacing later as an obscure lookup error."""
    names = [name.strip() for name in value.split(",") if name.strip()]
    if not names:
        raise argparse.ArgumentTypeError("at least one source is required")
    unknown = [name for name in names if name not in SOURCE_NAMES]
    if unknown:
        raise argparse.ArgumentTypeError(
            "unknown source(s): %s (choose from %s)"
            % (", ".join(unknown), ", ".join(SOURCE_NAMES))
        )
    return names


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
        help="replace the first word, then every N-th word after it (default: 5)",
    )
    parser.add_argument("-i", "--input", metavar="FILE", help="read text from FILE")
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help="write result to FILE (default with --input: FILE-modified)",
    )
    parser.add_argument(
        "-c", "--clip", action="store_true",
        help="read from and write back to the system clipboard",
    )
    parser.add_argument(
        "--slide", action="store_true",
        help="if the N-th word has no synonym, try the next word instead",
    )
    parser.add_argument(
        "--senses", type=int, default=3, metavar="K",
        help="consider the K closest word senses, not just the closest (default: 3)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.95, metavar="T",
        help="minimum sense similarity (0-1) a --senses candidate must clear, "
             "or that word is skipped/slid past (default: 0.95; only matters "
             "with --senses > 1, which is the default; 0 disables the check)",
    )
    parser.add_argument(
        "--multiword", action="store_true",
        help="allow multi-word synonyms such as 'give up'",
    )
    parser.add_argument(
        "--sources", type=source_list, default=list(DEFAULT_SOURCES), metavar="NAME[,NAME...]",
        help="synonym source(s) to use, comma-separated (default: wordnet); "
             "see below for the full list",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="list each substitution on stderr",
    )
    parser.add_argument("--version", action="version", version="synreplace " + __version__)
    return parser


# Input sources for which the result is also echoed to stdout, on top of
# whatever write_output() does with it -- there is no other way to see it for
# --clip, and it is the expected instant-feedback behaviour for a TEXT arg.
ECHOED_SOURCES = frozenset({"clip", "text"})


def read_input(args: argparse.Namespace):
    """Resolve the input source, most explicit first. Returns (text, source)."""
    if args.clip:
        return paste(), "clip"
    if args.input:
        if args.input == "-":
            return sys.stdin.read(), "stdin"
        with open(args.input, "r", encoding="utf-8") as handle:
            return handle.read(), "file"
    if args.text:
        return " ".join(args.text), "text"
    # Not a terminal means something is piped in, so read it without prompting.
    if not sys.stdin.isatty():
        return sys.stdin.read(), "stdin"
    print("Paste your text, then press Ctrl-D to rewrite it:", file=sys.stderr)
    return sys.stdin.read(), "interactive"


def _print_to_stdout(text: str) -> None:
    sys.stdout.write(text)
    # Keep the shell prompt on its own line without altering file/clipboard output.
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")


def write_output(args: argparse.Namespace, text: str, source: str) -> None:
    """Send the result where the flags say. Status messages go to stderr so
    that stdout stays clean for piping."""
    printed = False
    if args.clip:
        copy(text)
        print("Rewritten text copied to clipboard.", file=sys.stderr)
    elif args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
        print("Wrote %s" % args.output, file=sys.stderr)
    else:
        _print_to_stdout(text)
        printed = True

    # Clipboard and directly-typed text have no other way to show the result,
    # so echo it to stdout even when it already went to the clipboard or a file.
    if not printed and source in ECHOED_SOURCES:
        _print_to_stdout(text)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.every < 1:
        print("synreplace: -n/--every must be 1 or greater", file=sys.stderr)
        return 2
    if not 0 <= args.threshold <= 1:
        print("synreplace: --threshold must be between 0 and 1", file=sys.stderr)
        return 2

    # Modifying a real file (not stdin, not the clipboard) writes a sibling
    # file rather than dumping to stdout, unless the caller named -o explicitly.
    if args.input and args.input != "-" and not args.output and not args.clip:
        args.output = default_output_path(args.input)

    try:
        text, source = read_input(args)
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
        threshold=args.threshold,
        sources=args.sources,
    )

    try:
        write_output(args, result, source)
    except (OSError, ClipboardError) as error:
        print("synreplace: %s" % error, file=sys.stderr)
        return 1

    if args.verbose:
        for item in replacements:
            print(
                "  #%d %s -> %s (%.0f%% similar)"
                % (item.position, item.original, item.replacement, item.similarity * 100),
                file=sys.stderr,
            )
        print("%d substitution%s" % (len(replacements), "" if len(replacements) == 1 else "s"),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
