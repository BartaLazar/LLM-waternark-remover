"""synreplace REST API.

Run with:  uvicorn app.main:app --reload   (from web/backend/)
See web/docs/API.md for the full endpoint reference, or /docs once the
server is running for the interactive (Swagger) version of the same thing.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from synreplace import __version__ as synreplace_version
from synreplace.corpora import ensure_corpora

from . import schemas, service

API_VERSION = "v1"

DEFAULTS = schemas.Defaults(every=5, slide=False, senses=1, threshold=0.95, allow_multiword=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fetch WordNet/tagger/cmudict once at startup rather than on the first
    # request, so the first user isn't the one who pays for the download.
    ensure_corpora(quiet=True)
    yield


app = FastAPI(
    title="synreplace API",
    description="Replace every N-th word of a text with its closest WordNet synonym.",
    version="1.0.0",
    lifespan=lifespan,
)

# Permissive by default so the static frontend (or any other client) can call
# this from a different origin/port during development. Tighten allow_origins
# to your actual frontend's origin before deploying this publicly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/" + API_VERSION + "/health", response_model=schemas.HealthResponse, tags=["meta"])
def health() -> schemas.HealthResponse:
    """Liveness check -- always returns 200 if the server is up."""
    return schemas.HealthResponse(status="ok")


@app.get("/api/" + API_VERSION + "/info", response_model=schemas.InfoResponse, tags=["meta"])
def info() -> schemas.InfoResponse:
    """Library version and the default parameter values /rewrite uses."""
    return schemas.InfoResponse(
        synreplace_version=synreplace_version,
        api_version=API_VERSION,
        defaults=DEFAULTS,
    )


@app.post(
    "/api/" + API_VERSION + "/rewrite",
    response_model=schemas.RewriteResponse,
    responses={
        422: {
            "description": "A field failed validation -- empty/whitespace-only "
                            "text, or a parameter out of range (see response body)."
        },
    },
    tags=["rewrite"],
)
def rewrite_text(payload: schemas.RewriteRequest) -> schemas.RewriteResponse:
    """Run the synonym replacement and return the rewritten text plus every
    substitution that was made.

    `payload.text` is never blank here: `RewriteRequest`'s own validator
    already rejects empty/whitespace-only text with a 422 before this body runs.
    """
    result, replacements = service.process_rewrite(
        text=payload.text,
        every=payload.every,
        slide=payload.slide,
        senses=payload.senses,
        threshold=payload.threshold,
        allow_multiword=payload.allow_multiword,
    )
    return schemas.RewriteResponse(
        result=result,
        replacements=[schemas.Replacement(**item.__dict__) for item in replacements],
        substitution_count=len(replacements),
    )


# Serve the static frontend at "/", after every API route above so /api/...
# paths are matched first and never shadowed by the catch-all static mount.
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
