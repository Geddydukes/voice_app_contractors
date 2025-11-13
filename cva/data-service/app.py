from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException

MODULE_ROOT = Path(__file__).resolve().parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.append(str(MODULE_ROOT))

from ingestion import ContractorIngestor, load_sample_corpus
from lead_models import (
    CallLogRequest,
    CallLogResponse,
    LeadCallRecord,
    LeadCreateRequest,
    LeadCreateResponse,
    LeadListResponse,
    LeadMessageRecord,
    LeadRecord,
    MessageLogRequest,
    MessageLogResponse,
)
from schemas import QueryRequest, QueryResponse, QueryResult
from shared.leads import LeadNotFoundError, LeadStore
from shared.observability import instrument_app, sanitize_value
from vector_store import VectorStore

app = FastAPI(title="Data Service")
logger = instrument_app(app, "data-service")

_vector_store = VectorStore()
load_sample_corpus(_vector_store)
_ingestor = ContractorIngestor(_vector_store)
_lead_store = LeadStore()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "data"}


@app.post("/v1/rag/query", response_model=QueryResponse)
def rag_query(request: QueryRequest) -> QueryResponse:
    results = _vector_store.query(request.query, top_k=request.top_k)
    if not results:
        raise HTTPException(status_code=404, detail="No matching knowledge snippets found")
    return QueryResponse(
        results=[
            QueryResult(
                chunk_id=chunk.chunk_id,
                score=round(score, 4),
                text=chunk.text,
                source=chunk.source,
                metadata=chunk.metadata,
            )
            for chunk, score in results
        ]
    )


@app.post("/v1/rag/ingest/site")
def ingest_site(url: str, max_depth: int = 1) -> dict[str, int]:
    _ingestor.ingest_site(url, max_depth=max_depth)
    return {"total_chunks": _vector_store.total_chunks}


@app.post("/v1/leads", response_model=LeadCreateResponse)
def create_lead(request: LeadCreateRequest) -> LeadCreateResponse:
    record = _lead_store.create_lead(
        caller_name=request.caller_name,
        caller_phone=request.caller_phone,
        caller_email=request.caller_email,
        transcript=request.transcript,
        summary=request.summary,
        appointment_time=request.appointment_time,
    )
    logger.info(
        "Lead created caller=%s", sanitize_value(request.caller_phone)
    )
    return LeadCreateResponse(lead=LeadRecord.model_validate(record))


@app.get("/v1/leads", response_model=LeadListResponse)
def list_leads() -> LeadListResponse:
    leads = [LeadRecord.model_validate(lead) for lead in _lead_store.list_leads()]
    return LeadListResponse(leads=leads)


@app.get("/v1/leads/{lead_id}", response_model=LeadRecord)
def get_lead(lead_id: int) -> LeadRecord:
    try:
        record = _lead_store.get_lead(lead_id)
    except LeadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LeadRecord.model_validate(record)


@app.post("/v1/leads/{lead_id}/calls", response_model=CallLogResponse)
def log_call(lead_id: int, request: CallLogRequest) -> CallLogResponse:
    try:
        record = _lead_store.record_call(
            lead_id,
            call_sid=request.call_sid,
            direction=request.direction,
            started_at=request.started_at,
            ended_at=request.ended_at,
            duration_seconds=request.duration_seconds,
            transcript=request.transcript,
            summary=request.summary,
        )
    except LeadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info("Call logged lead=%s", lead_id)
    return CallLogResponse(call=LeadCallRecord.model_validate(record))


@app.post("/v1/leads/{lead_id}/messages", response_model=MessageLogResponse)
def log_message(lead_id: int, request: MessageLogRequest) -> MessageLogResponse:
    try:
        message = _lead_store.record_message(
            lead_id,
            direction=request.direction,
            channel=request.channel,
            recipient=request.recipient,
            body=request.body,
            template=request.template,
            status=request.status,
            metadata=request.metadata,
        )
    except LeadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info("Message recorded lead=%s channel=%s", lead_id, request.channel)
    return MessageLogResponse(message=LeadMessageRecord.model_validate(message.__dict__))


@app.post("/v1/rag/ingest/local")
def ingest_local(directory: str) -> dict[str, int]:
    base = Path(directory)
    if not base.exists():
        raise HTTPException(status_code=400, detail="Directory does not exist")
    _ingestor.ingest_local_site(base)
    documents_dir = base / "documents"
    if documents_dir.exists():
        _ingestor.ingest_documents(documents_dir)
    faq_path = base / "faq.json"
    if faq_path.exists():
        _ingestor.ingest_faq(faq_path)
    return {"total_chunks": _vector_store.total_chunks}
