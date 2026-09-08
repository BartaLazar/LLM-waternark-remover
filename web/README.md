# synreplace web interface

A browser UI and REST API for `synreplace`, kept in this folder so its code
runs independently of the CLI: this is a separate app that happens to reuse
the same `synreplace` engine, not a dependency of the CLI itself.

It shares the **one virtual environment at the repo root** with the CLI
(see the top-level [`README.md`](../README.md)) rather than keeping its own:
one `.venv`, one `requirements.txt`, for the whole project.

- **Backend**: FastAPI, in `backend/`. Wraps the same `synreplace` engine the
  CLI uses (`synreplace.rewrite()`) behind a REST API, and serves the static
  frontend alongside it.
- **Frontend**: plain HTML/CSS/JS, in `frontend/`, no build step, no
  framework, no external assets, fonts included (works offline once the API
  is running, as long as you stick to the WordNet source; see below). A
  Ribbon selector switches the result between three views (plain, inline
  corrections, or side-by-side with the original); the correction card under
  each changed word lets you reset it or swap in one of up to 3 alternative
  synonyms, with every view updating live.
- **Synonym sources**: WordNet (offline, default), or Datamuse, a free online
  dictionary API that needs no key/signup. Pick one or both in the UI's
  "Sources" checkboxes; using both pools their candidates together. See
  [`docs/API.md`](docs/API.md#synonym-sources) for the trade-offs (network
  latency, no sense-disambiguation on the online source).
- **API reference**: see [`docs/API.md`](docs/API.md) for the full endpoint
  documentation, or run the server and open `/docs` for the live,
  auto-generated (Swagger) version of the same thing.

## Setup

From the **repo root** (not this folder): one venv covers the CLI and the
web interface:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                # the synreplace CLI package itself
pip install -r requirements.txt # nltk + the web interface's fastapi/uvicorn/pydantic
```

If you already set this up for the CLI, there's nothing extra to install:
`requirements.txt` at the repo root covers both.

## Run

```bash
source .venv/bin/activate       # from the repo root
cd web/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The first run downloads WordNet/tagger/pronunciation data the same way the
CLI does (a few seconds, one time only).

Then open **http://127.0.0.1:8000** in a browser for the UI, or call the API
directly at `http://127.0.0.1:8000/api/v1/...` (see
[`docs/API.md`](docs/API.md)). The server binds to `127.0.0.1` only, so it
is not reachable from other machines on your network by default.

Pass `--reload` during development to auto-restart on code changes:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Folder layout

```
web/
├── backend/
│   └── app/
│       ├── main.py       # FastAPI app: routes, CORS, startup, static mount
│       ├── schemas.py    # Request/response models (also drive the OpenAPI docs)
│       └── service.py    # Thin wrapper around synreplace.rewrite()
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js            # Calls the REST API via fetch()
├── docs/
│   └── API.md             # Full API reference
└── README.md               # This file
```

(No `requirements.txt` here: dependencies live in the repo root's, shared
with the CLI.)
