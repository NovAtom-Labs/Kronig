"""Knowledge source, passage, citation, and retrieval schemas."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from tcad_agent.domain.models import StrictModel


class SourceManifest(StrictModel):
    id: str
    title: str
    url: str
    license: str = Field(min_length=1)
    access: Literal["public", "restricted"]
    trust: Literal["primary", "secondary", "internal-reviewed"]
    backend: Literal["devsim", "sentaurus", "portable"]
    version: str
    compatible_versions: tuple[str, ...] = ()
    reviewed: bool = False
    local_path: str | None = None


class Passage(StrictModel):
    id: str
    source_id: str
    title: str
    url: str
    license: str
    access: Literal["public", "restricted"]
    trust: Literal["primary", "secondary", "internal-reviewed"]
    backend: Literal["devsim", "sentaurus", "portable"]
    version: str
    compatible_versions: tuple[str, ...] = ()
    reviewed: bool
    content: str
    content_hash: str

    @classmethod
    def create(cls, **data: object) -> Passage:
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("passage content must be non-empty")
        return cls.model_validate(
            data | {"content_hash": hashlib.sha256(content.encode()).hexdigest()}
        )


class Citation(StrictModel):
    source_id: str
    title: str
    url: str
    version: str
    content_hash: str


class SearchHit(StrictModel):
    id: str
    content: str
    backend: str
    score: float
    reviewed: bool
    citation: Citation


class WebSearchResult(StrictModel):
    query: str
    title: str
    url: str
    snippet: str
    authority: Literal["primary", "scholarly", "community", "unknown"]


class WebEvidenceRecord(StrictModel):
    title: str
    url: str
    content_type: str
    content: str
    content_hash: str
    retrieved_at: datetime
    query: str = ""
    authority: Literal["primary", "scholarly", "community", "unknown"]
    backend: str | None = None
    version: str | None = None
    untrusted_content: bool = True
    from_cache: bool = False

    @classmethod
    def create(cls, **data: object) -> WebEvidenceRecord:
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("web evidence content must be non-empty")
        return cls.model_validate(
            data
            | {
                "content_hash": hashlib.sha256(content.encode()).hexdigest(),
                "retrieved_at": datetime.now(UTC),
            }
        )
