"""Request/response models for the REST API.

FastAPI validates every request against these before an endpoint ever runs,
and turns them into the interactive OpenAPI docs at /docs -- so field
constraints and descriptions here are also user-facing documentation.
"""

from typing import List

from pydantic import BaseModel, Field, field_validator


class RewriteRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        description="The text to rewrite.",
        examples=["The quick brown fox jumps over the lazy dog."],
    )
    every: int = Field(
        5, ge=1,
        description="Replace every N-th word.",
    )
    slide: bool = Field(
        False,
        description="If the N-th word has no usable synonym, try the next "
                     "word instead of leaving that slot unfilled.",
    )
    senses: int = Field(
        3, ge=1,
        description="Consider the K closest WordNet senses of a word, not "
                     "just its single most common one.",
    )
    threshold: float = Field(
        0.95, ge=0.0, le=1.0,
        description="Minimum similarity (0-1) a non-dominant sense must "
                     "have to the word's dominant sense to be used; 0 "
                     "disables the check. Only matters when senses > 1, "
                     "which is the default.",
    )
    allow_multiword: bool = Field(
        False,
        description="Allow multi-word synonyms such as 'give up'.",
    )

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must contain at least one non-whitespace character")
        return value


class Replacement(BaseModel):
    position: int = Field(description="1-based index of the word within the text.")
    original: str = Field(description="The original word at that position.")
    replacement: str = Field(description="The synonym it was replaced with.")
    similarity: float = Field(
        description="The replacement's WordNet sense similarity (0-1) to the "
                     "word's dominant sense. Always 1.0 unless senses > 1 "
                     "pulled the winning candidate from a less common sense."
    )


class RewriteResponse(BaseModel):
    result: str = Field(description="The rewritten text.")
    replacements: List[Replacement] = Field(
        description="Every substitution that was made, in text order."
    )
    substitution_count: int = Field(description="len(replacements), for convenience.")


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])


class Defaults(BaseModel):
    every: int
    slide: bool
    senses: int
    threshold: float
    allow_multiword: bool


class InfoResponse(BaseModel):
    synreplace_version: str
    api_version: str
    defaults: Defaults
