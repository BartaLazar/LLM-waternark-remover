# synreplace REST API reference

Base URL (default): `http://127.0.0.1:8000`

This document is the hand-written reference. The same information is also
available live, generated straight from the code, once the server is running:

- **Swagger UI** (interactive, try-it-out): `http://127.0.0.1:8000/docs`
- **ReDoc** (read-only, cleaner for long docs): `http://127.0.0.1:8000/redoc`
- **Raw OpenAPI schema** (JSON): `http://127.0.0.1:8000/openapi.json`

If this file and the live docs ever disagree, trust the live docs — they're
generated from the request/response models in `web/backend/app/schemas.py`,
so they can't drift out of sync with the actual API the way hand-written docs can.

## Contents

- [Conventions](#conventions)
- [Authentication](#authentication)
- [CORS](#cors)
- [Endpoints](#endpoints)
  - [`GET /api/v1/health`](#get-apiv1health)
  - [`GET /api/v1/info`](#get-apiv1info)
  - [`POST /api/v1/rewrite`](#post-apiv1rewrite)
- [Synonym sources](#synonym-sources)
- [Error format](#error-format)
- [Versioning](#versioning)

## Conventions

- All request and response bodies are JSON (`Content-Type: application/json`).
- All endpoints are namespaced under `/api/v1`.
- Field names are `snake_case` on the wire, matching the Python models.
- There is no pagination, no persistent state, and nothing is stored between
  requests — every call is independent.

## Authentication

None. The API has no login, API keys, or sessions — every endpoint is open to
whoever can reach the server. This is intentional for a local/offline tool; if
you deploy this somewhere reachable by other people, put it behind your own
auth layer (reverse proxy, API gateway, etc.) — the app itself does not
provide one.

## CORS

The server sends permissive CORS headers (`Access-Control-Allow-Origin: *`) by
default, so the bundled frontend — or any other page — can call it from a
different origin during development. See `app.add_middleware(CORSMiddleware, ...)`
in `web/backend/app/main.py:1` if you need to restrict this before deploying
publicly.

---

## Endpoints

### `GET /api/v1/health`

Liveness check. No parameters.

**Response `200`**

```json
{ "status": "ok" }
```

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | Always `"ok"` if the server responds at all. |

---

### `GET /api/v1/info`

Library version and the default parameter values the `/rewrite` endpoint
uses when a field is omitted. Useful for a client to prefill a form without
hardcoding defaults that could drift from the server's.

**Response `200`**

```json
{
  "synreplace_version": "0.1.0",
  "api_version": "v1",
  "defaults": {
    "every": 5,
    "slide": false,
    "senses": 3,
    "threshold": 0.95,
    "allow_multiword": false,
    "sources": ["wordnet"]
  },
  "available_sources": [
    {
      "name": "wordnet",
      "description": "Standard dictionary (WordNet, offline, no network needed)",
      "online": false
    },
    {
      "name": "datamuse",
      "description": "Datamuse API (online, no key needed)",
      "online": true
    },
    {
      "name": "dictionaryapi",
      "description": "Free Dictionary API (online, no key needed)",
      "online": true
    }
  ]
}
```

| Field | Type | Description |
| --- | --- | --- |
| `synreplace_version` | string | Version of the underlying `synreplace` package (`synreplace.__version__`). |
| `api_version` | string | This API's version segment, e.g. `"v1"` — matches the URL prefix. |
| `defaults` | object | The default value `/rewrite` uses for each optional field. Shape matches the `RewriteRequest` fields below (minus `text`). |
| `available_sources` | array of `SourceInfo` | Every valid value for `RewriteRequest.sources`, with a human-readable description and whether it needs a network connection. |

---

### `POST /api/v1/rewrite`

Runs the synonym replacement and returns the rewritten text plus a record of
every substitution made. This is the same engine the CLI uses
(`synreplace.rewrite()`), so a request with equivalent parameters produces
byte-identical output to the CLI.

**Request body** (`RewriteRequest`)

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `text` | string | yes | — | non-empty after trimming whitespace | The text to rewrite. |
| `every` | integer | no | `5` | `>= 1` | Replace the first word, then every N-th word after it (word 1, `1+N`, `1+2N`, ...). |
| `slide` | boolean | no | `false` | — | If a targeted word has no usable synonym, try the next word instead of leaving that slot unfilled. Keeps the substitution rate close to 1-in-N; without it, substitutions land only on the fixed grid (word 1, `1+N`, `1+2N`, ...) and misses are common. |
| `senses` | integer | no | `3` | `>= 1` | Consider the K closest WordNet senses of a word, not just its single most common one. `1` never looks past the dominant sense. |
| `threshold` | number | no | `0.95` | `0.0`–`1.0` | Minimum Wu-Palmer similarity a non-dominant sense must have to the word's dominant sense to be used as a candidate; `0` disables the check. **Only has any effect when `senses > 1`**, which is the default — at `senses=1` a word's only sense is trivially 100% similar to itself, so every candidate already clears any threshold. |
| `allow_multiword` | boolean | no | `false` | — | Allow multi-word synonyms such as `"give up"`. |
| `sources` | array of string | no | `["wordnet"]` | non-empty; each name must be one from [`/info`](#get-apiv1info)'s `available_sources` | One or more synonym sources to use. Naming more than one pools their candidates together rather than picking one. `senses`/`threshold` only affect the `wordnet` source. See [Synonym sources](#synonym-sources) below. |

Example (omitted fields use their defaults, shown in [`/info`](#get-apiv1info) above):

```json
{
  "text": "The quick brown fox jumps over the lazy dog.",
  "every": 3,
  "slide": true
}
```

**Response `200`** (`RewriteResponse`)

| Field | Type | Description |
| --- | --- | --- |
| `result` | string | The rewritten text. Whitespace, punctuation, and numbers are preserved byte-for-byte outside of the replaced words. |
| `replacements` | array of `Replacement` | Every substitution made, in text order. Empty if nothing was replaceable. |
| `substitution_count` | integer | `len(replacements)`, provided for convenience. |
| `tokens` | array of `TextToken` | The full text broken into words and the gaps between them, in order — see below. |

**`Replacement` object**

| Field | Type | Description |
| --- | --- | --- |
| `position` | integer | 1-based index of the word within the text (counting every word, not just replaced ones). Matches a `TextToken.position` below. |
| `original` | string | The original word at that position. |
| `replacement` | string | The synonym it was replaced with, re-inflected and re-cased to match the original. |
| `similarity` | number | The replacement's WordNet sense similarity (`0.0`–`1.0`) to the word's dominant sense. Always `1.0` unless `senses > 1` pulled the winning candidate from a less common sense. |
| `alternatives` | array of `Alternative` | Up to 3 other valid synonyms for this word, best first, excluding `replacement` itself. Empty if none qualified. Intended for a picker UI — see the web frontend's "Other choices" column. |

**`Alternative` object**

| Field | Type | Description |
| --- | --- | --- |
| `word` | string | An alternative synonym, already re-inflected and re-cased like `replacement`. |
| `similarity` | number | Same meaning as `Replacement.similarity`. |

**`TextToken` object**

Every token of the *rewritten* text — words and the whitespace/punctuation
between them — so a client can edit one word (reset it to `original`, swap in
an `alternative`) and reconstruct `result` by concatenating every token's
`text`, without re-implementing word-boundary detection.

| Field | Type | Description |
| --- | --- | --- |
| `text` | string | The token's literal text. |
| `is_word` | boolean | `false` for a whitespace/punctuation gap between words. |
| `position` | integer or `null` | 1-based word ordinal (matches `Replacement.position`), or `null` for a non-word token. |

Example response for the request above (`every: 3, slide: true`, everything
else default), captured from the running server:

```json
{
  "result": "The speedy brown fox leaps over the lazy dog.",
  "replacements": [
    {
      "position": 2,
      "original": "quick",
      "replacement": "speedy",
      "similarity": 1.0,
      "alternatives": []
    },
    {
      "position": 5,
      "original": "jumps",
      "replacement": "leaps",
      "similarity": 1.0,
      "alternatives": [
        { "word": "springs", "similarity": 1.0 },
        { "word": "bounds", "similarity": 1.0 }
      ]
    }
  ],
  "substitution_count": 2,
  "tokens": [
    { "text": "The", "is_word": true, "position": 1 },
    { "text": " ", "is_word": false, "position": null },
    { "text": "speedy", "is_word": true, "position": 2 },
    { "text": " ", "is_word": false, "position": null },
    { "text": "brown", "is_word": true, "position": 3 },
    { "text": " ", "is_word": false, "position": null },
    { "text": "fox", "is_word": true, "position": 4 },
    { "text": " ", "is_word": false, "position": null },
    { "text": "leaps", "is_word": true, "position": 5 },
    { "text": " ", "is_word": false, "position": null },
    { "text": "over", "is_word": true, "position": 6 },
    { "text": " ", "is_word": false, "position": null },
    { "text": "the", "is_word": true, "position": 7 },
    { "text": " ", "is_word": false, "position": null },
    { "text": "lazy", "is_word": true, "position": 8 },
    { "text": " ", "is_word": false, "position": null },
    { "text": "dog", "is_word": true, "position": 9 },
    { "text": ".", "is_word": false, "position": null }
  ]
}
```

**Errors**

| Status | When | Example body |
| --- | --- | --- |
| `422` | `text` is missing, empty, or whitespace-only; `sources` is empty or names an unknown source; or any field fails its type/range constraint (e.g. `threshold: 1.5`, `every: 0`). | See [Error format](#error-format) below. |
| `500` | Unexpected server-side failure. Shouldn't happen in normal operation; check server logs if it does. | `{"detail": "Internal Server Error"}` |

**curl example**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/rewrite \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The researchers carefully examined the surprising results.",
    "every": 3,
    "slide": true,
    "sources": ["wordnet", "datamuse"]
  }'
```

---

## Synonym sources

`sources` selects one or more synonym sources by name (see `/info`'s
`available_sources` for the live list). Naming more than one pools every
enabled source's candidates into one ranked list, rather than picking exactly
one to use.

| Name | What it is | Network? |
| --- | --- | --- |
| `wordnet` | Offline WordNet lookup (the default) | No |
| `datamuse` | [Datamuse](https://www.datamuse.com/api/), built specifically for word-relation queries; returns a relevance score per candidate | Yes |
| `dictionaryapi` | [Free Dictionary API](https://dictionaryapi.dev/), a definitions API with synonyms as a secondary field; coverage varies a lot by word, and it reports no per-candidate score (every candidate shows `similarity: 1.0`) | Yes |

Trade-offs worth knowing:

- **Latency.** Each distinct word costs one HTTP request per online source
  (cached per source instance for the process's lifetime, so a repeated word
  is free the second time). A slow or unreachable API adds real time to a
  request rather than erroring it out — a source that fails just contributes
  no candidates for that request, and prints a one-time note to the server's
  stderr the first time that happens.
- **`senses`/`threshold` only affect `wordnet`.** The online APIs have no
  notion of "the word's Kth-closest sense" — Datamuse in particular doesn't
  disambiguate senses at all, so it can surface a synonym for the wrong
  meaning of a word in a way `threshold` can't filter for that source.
- **`similarity` isn't on the same scale across sources.** WordNet's is a
  graph-distance score, Datamuse's is a normalized relevance score, and
  `dictionaryapi`'s is a fixed `1.0` for every candidate. All three are
  reported as a `0.0`–`1.0` float for a consistent shape, but the numbers
  aren't measuring the same thing.

## Error format

Validation failures (`422`) use FastAPI/Pydantic's standard shape — a `detail`
array, one entry per failing field. Captured directly from the running server:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "text"],
      "msg": "Value error, text must contain at least one non-whitespace character",
      "input": "   ",
      "ctx": { "error": {} }
    }
  ]
}
```

```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["body", "threshold"],
      "msg": "Input should be less than or equal to 1",
      "input": 1.5,
      "ctx": { "le": 1.0 }
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `type` | Machine-readable error category (`value_error`, `missing`, `less_than_equal`, `greater_than_equal`, ...). |
| `loc` | Path to the offending field, e.g. `["body", "threshold"]`. |
| `msg` | Human-readable explanation. |
| `input` | The value that was rejected. |
| `ctx` | Extra machine-readable context for the failure (e.g. the limit that was violated). Shape varies by `type`. |

Multiple fields can fail at once — `detail` will contain one entry per failure.

## Versioning

The URL path carries the version (`/api/v1/...`). A breaking change to the
request/response shape would ship as `/api/v2/...` alongside the existing
`v1` routes rather than changing `v1`'s behavior underneath existing clients.
Non-breaking additions (a new optional field, a new endpoint) can land in
`v1` directly.
