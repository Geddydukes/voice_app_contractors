from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List


_TOKEN_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


@dataclass
class TextChunk:
    chunk_id: str
    text: str
    source: str
    metadata: dict[str, str]


@dataclass
class _StoredChunk:
    chunk: TextChunk
    counter: Counter[str]
    total_terms: int


class VectorStore:
    """Lightweight in-memory vector store using TF-IDF cosine similarity."""

    def __init__(self) -> None:
        self._chunks: list[_StoredChunk] = []
        self._document_frequency: Counter[str] = Counter()

    def add_text(self, text: str, source: str, metadata: dict[str, str] | None = None) -> TextChunk:
        metadata = metadata or {}
        tokens = _tokenize(text)
        if not tokens:
            raise ValueError("Cannot index empty text chunk")
        counter = Counter(tokens)
        unique_tokens = set(counter)
        self._document_frequency.update(unique_tokens)
        chunk = TextChunk(chunk_id=str(uuid.uuid4()), text=text, source=source, metadata=metadata)
        self._chunks.append(_StoredChunk(chunk=chunk, counter=counter, total_terms=sum(counter.values())))
        return chunk

    @property
    def total_chunks(self) -> int:
        return len(self._chunks)

    def _idf(self, token: str) -> float:
        # +1 smoothing prevents divide-by-zero for novel tokens.
        df = self._document_frequency.get(token, 0)
        if not self._chunks:
            return 0.0
        return math.log((1 + len(self._chunks)) / (1 + df)) + 1.0

    def _chunk_norm(self, stored: _StoredChunk) -> float:
        return math.sqrt(
            sum(
                self._tfidf_weight(token, count, stored.total_terms) ** 2
                for token, count in stored.counter.items()
            )
        )

    def _tfidf_weight(self, token: str, count: int, total_terms: int) -> float:
        if total_terms == 0:
            return 0.0
        tf = count / total_terms
        return tf * self._idf(token)

    def query(self, text: str, top_k: int = 3) -> list[tuple[TextChunk, float]]:
        tokens = _tokenize(text)
        if not tokens:
            return []
        query_counter = Counter(tokens)
        total_terms = sum(query_counter.values())
        query_weights = {
            token: self._tfidf_weight(token, count, total_terms)
            for token, count in query_counter.items()
        }
        query_norm = math.sqrt(sum(weight ** 2 for weight in query_weights.values())) or 1.0
        scored: list[tuple[TextChunk, float]] = []
        for stored in self._chunks:
            numerator = 0.0
            for token, query_weight in query_weights.items():
                if token not in stored.counter:
                    continue
                numerator += query_weight * self._tfidf_weight(
                    token, stored.counter[token], stored.total_terms
                )
            if numerator <= 0.0:
                continue
            denominator = query_norm * (self._chunk_norm(stored) or 1.0)
            score = numerator / denominator if denominator else 0.0
            if score > 0.0:
                scored.append((stored.chunk, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def iter_chunks(self) -> Iterable[TextChunk]:
        for stored in self._chunks:
            yield stored.chunk
