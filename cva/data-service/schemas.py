from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(3, ge=1, le=10)


class QueryResult(BaseModel):
    chunk_id: str
    score: float
    text: str
    source: str
    metadata: dict[str, Any]


class QueryResponse(BaseModel):
    results: list[QueryResult]
