"""One-time download of the NLTK data synreplace depends on."""

import sys

# (probe path, download id) pairs. The tagger was renamed in NLTK 3.9, so both
# spellings are tried and the first that resolves wins.
REQUIRED = [
    (("corpora/wordnet.zip", "corpora/wordnet"), ("wordnet",)),
    (("corpora/omw-1.4.zip", "corpora/omw-1.4"), ("omw-1.4",)),
    (
        ("taggers/averaged_perceptron_tagger_eng", "taggers/averaged_perceptron_tagger"),
        ("averaged_perceptron_tagger_eng", "averaged_perceptron_tagger"),
    ),
]


def _present(paths) -> bool:
    import nltk

    for path in paths:
        try:
            nltk.data.find(path)
            return True
        except LookupError:
            continue
    return False


def ensure_corpora(quiet: bool = False) -> None:
    """Download any missing WordNet/tagger data, once, into ~/nltk_data."""
    import nltk

    announced = False
    for paths, package_ids in REQUIRED:
        if _present(paths):
            continue
        if not announced and not quiet:
            print("Downloading WordNet data (first run only)...", file=sys.stderr)
            announced = True
        for package_id in package_ids:
            if nltk.download(package_id, quiet=True):
                break
        if not _present(paths):
            raise SystemExit(
                "Could not download NLTK data '%s'. Check your network connection, "
                "or fetch it manually with:\n"
                "    python -m nltk.downloader %s" % (package_ids[0], package_ids[0])
            )
