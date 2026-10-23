"""Immutable SQLite FTS5 index with optional semantic reciprocal-rank fusion."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Protocol

from tcad_agent.knowledge.models import Citation, Passage, SearchHit


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class FastEmbedProvider:
    """Lazy FastEmbed adapter so lexical-only operation needs no model download."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return tuple(tuple(float(value) for value in vector) for vector in self._model.embed(texts))


class KnowledgeIndex:
    def __init__(self, path: Path, embedder: EmbeddingProvider | None = None) -> None:
        self.path = path
        self.embedder = embedder

    @classmethod
    def build(
        cls,
        path: Path,
        passages: Sequence[Passage],
        embedder: EmbeddingProvider | None = None,
    ) -> KnowledgeIndex:
        if path.exists():
            raise FileExistsError(f"knowledge index already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        embeddings: Sequence[Sequence[float] | None]
        if embedder is None:
            embeddings = (None,) * len(passages)
        else:
            embeddings = tuple(embedder.embed([passage.content for passage in passages]))
            if len(embeddings) != len(passages):
                raise ValueError("embedding provider returned the wrong number of vectors")
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE passages (
                    id TEXT UNIQUE NOT NULL,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    license TEXT NOT NULL,
                    access TEXT NOT NULL,
                    trust TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    version TEXT NOT NULL,
                    compatible_versions TEXT NOT NULL,
                    reviewed INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding TEXT
                );
                CREATE VIRTUAL TABLE passages_fts USING fts5(
                    content,
                    content='passages',
                    content_rowid='rowid'
                );
                """
            )
            for passage, embedding in zip(passages, embeddings, strict=True):
                connection.execute(
                    """INSERT INTO passages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        passage.id,
                        passage.source_id,
                        passage.title,
                        passage.url,
                        passage.license,
                        passage.access,
                        passage.trust,
                        passage.backend,
                        passage.version,
                        json.dumps(passage.compatible_versions),
                        int(passage.reviewed),
                        passage.content,
                        passage.content_hash,
                        json.dumps(embedding) if embedding is not None else None,
                    ),
                )
            connection.execute("INSERT INTO passages_fts(passages_fts) VALUES ('rebuild')")
        return cls(path, embedder)

    def search(
        self,
        query: str,
        filters: dict[str, str] | None = None,
        limit: int = 5,
    ) -> tuple[SearchHit, ...]:
        if limit <= 0:
            return ()
        tokens = re.findall(r"[A-Za-z0-9_]+", query.lower())
        if not tokens:
            return ()
        active_filters = filters or {}
        clauses: list[str] = []
        parameters: list[str] = []
        for field in ("backend", "access"):
            if field in active_filters:
                clauses.append(f"p.{field} = ?")
                parameters.append(active_filters[field])
        if "version" in active_filters:
            clauses.append(
                "(p.version = ? OR EXISTS ("
                "SELECT 1 FROM json_each(p.compatible_versions) "
                "WHERE json_each.value = ?))"
            )
            parameters.extend((active_filters["version"], active_filters["version"]))
        where = " AND " + " AND ".join(clauses) if clauses else ""
        fts_query = " OR ".join(f'"{token}"' for token in tokens)
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            lexical = connection.execute(
                """SELECT p.*, bm25(passages_fts) AS lexical_score
                   FROM passages_fts
                   JOIN passages p ON p.rowid = passages_fts.rowid
                   WHERE passages_fts MATCH ?"""
                + where
                + " ORDER BY lexical_score LIMIT 100",
                [fts_query, *parameters],
            ).fetchall()
        if not lexical:
            return ()
        lexical_rank = {row["id"]: rank for rank, row in enumerate(lexical, start=1)}
        semantic_rank: dict[str, int] = {}
        if self.embedder is not None:
            query_vector = tuple(float(value) for value in self.embedder.embed([query])[0])
            semantic = sorted(
                (
                    (row["id"], self._cosine(query_vector, tuple(json.loads(row["embedding"]))))
                    for row in lexical
                    if row["embedding"] is not None
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            semantic_rank = {identifier: rank for rank, (identifier, _) in enumerate(semantic, 1)}
        trust_bonus = {"primary": 0.004, "internal-reviewed": 0.003, "secondary": 0.0}
        hits: list[SearchHit] = []
        for row in lexical:
            score = 1.0 / (60 + lexical_rank[row["id"]])
            if row["id"] in semantic_rank:
                score += 1.0 / (60 + semantic_rank[row["id"]])
            score += 0.01 if row["reviewed"] else 0.0
            score += trust_bonus.get(row["trust"], 0.0)
            hits.append(
                SearchHit(
                    id=row["id"],
                    content=row["content"],
                    backend=row["backend"],
                    score=score,
                    reviewed=bool(row["reviewed"]),
                    citation=Citation(
                        source_id=row["source_id"],
                        title=row["title"],
                        url=row["url"],
                        version=row["version"],
                        content_hash=row["content_hash"],
                    ),
                )
            )
        ranked = sorted(hits, key=lambda hit: (-hit.score, hit.id))
        if limit == 1:
            return tuple(ranked[:1])

        selected: list[SearchHit] = []
        selected_ids: set[str] = set()
        selected_sources: set[str] = set()
        for hit in ranked:
            source_id = hit.citation.source_id
            if source_id in selected_sources:
                continue
            selected.append(hit)
            selected_ids.add(hit.id)
            selected_sources.add(source_id)
            if len(selected) == limit:
                return tuple(selected)
        for hit in ranked:
            if hit.id in selected_ids:
                continue
            selected.append(hit)
            if len(selected) == limit:
                break
        return tuple(selected)

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
            sum(value * value for value in right)
        )
        if denominator == 0:
            return 0.0
        return sum(a * b for a, b in zip(left, right, strict=True)) / denominator
