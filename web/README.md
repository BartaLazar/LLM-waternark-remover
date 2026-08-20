# synreplace web interface

A browser UI and REST API for `synreplace`, kept in this folder so it runs
independently of the CLI — nothing here is required to use `synreplace` from
the command line, and nothing in `synreplace/` is required to run this beyond
the library itself.

- **Backend**: FastAPI, in `backend/`. Wraps the same `synreplace` engine the
  CLI uses (`synreplace.rewrite()`) behind a REST API, and serves the static
  frontend alongside it.
- **Frontend**: plain HTML/CSS/JS, in `frontend/` — no build step, no
  framework, no external assets (works offline once the API is running).
- **API reference**: see [`docs/API.md`](docs/API.md) for the full endpoint
  documentation, or run the server and open `/docs` for the live,
  auto-generated (Swagger) version of the same thing.

## Setup

The backend needs the `synreplace` package installed (editable, so it always
reflects the current checkout) alongside its own dependencies:

```bash
cd web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../..        # installs the synreplace CLI package itself
```

## Run

```bash
cd web/backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The first run downloads WordNet/tagger/pronunciation data the same way the
CLI does (a few seconds, one time only).

Then open **http://127.0.0.1:8000** in a browser for the UI, or call the API
directly at `http://127.0.0.1:8000/api/v1/...` (see
[`docs/API.md`](docs/API.md)). The server binds to `127.0.0.1` only — it is
not reachable from other machines on your network by default.

Pass `--reload` during development to auto-restart on code changes:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Folder layout

```
web/
├── backend/
│   ├── app/
│   │   ├── main.py       # FastAPI app: routes, CORS, startup, static mount
│   │   ├── schemas.py    # Request/response models (also drive the OpenAPI docs)
│   │   └── service.py    # Thin wrapper around synreplace.rewrite()
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js            # Calls the REST API via fetch()
├── docs/
│   └── API.md             # Full API reference
└── README.md               # This file
```
