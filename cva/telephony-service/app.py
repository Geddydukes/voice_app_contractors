from __future__ import annotations

import base64
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Dict
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

# Ensure shared libraries are importable when running the service standalone
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from shared.observability import (  # noqa: E402
    generate_trace_id,
    instrument_app,
    reset_trace_id,
    sanitize_value,
    set_trace_id,
)
from shared.streaming import AudioChunk  # noqa: E402

from models import CallSessionResponse, InboundCallRequest
from pipeline import StreamingPipeline

app = FastAPI(title="Telephony Service", version="0.1.0")
logger = instrument_app(app, "telephony-service")


@dataclass
class CallSessionState:
    payload: InboundCallRequest
    trace_id: str


pipeline = StreamingPipeline()
call_sessions: Dict[str, CallSessionState] = {}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "telephony"}


@app.post("/v1/calls/inbound", response_model=CallSessionResponse)
async def inbound_call(payload: InboundCallRequest) -> CallSessionResponse:
    session_id = uuid4().hex
    trace_id = generate_trace_id()
    call_sessions[session_id] = CallSessionState(payload=payload, trace_id=trace_id)
    logger.info(
        "Inbound call created session=%s from=%s to=%s",
        session_id,
        sanitize_value(payload.from_number),
        sanitize_value(payload.to_number),
    )
    stream_url = f"/v1/calls/stream/{session_id}"
    return CallSessionResponse(
        session_id=session_id,
        stream_url=stream_url,
        trace_id=trace_id,
    )


@app.websocket("/v1/calls/stream/{session_id}")
async def call_stream(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session_state = call_sessions.get(session_id)
    if session_state is None:
        await websocket.close(code=4404)
        return

    async def audio_stream() -> AsyncIterator[AudioChunk]:
        sequence = 0
        try:
            while True:
                message = await websocket.receive_text()
                frame = base64.b64decode(message)
                yield AudioChunk(
                    session_id=session_id,
                    sequence=sequence,
                    sample_rate=16000,
                    payload=frame,
                    trace_id=session_state.trace_id,
                )
                sequence += 1
        except WebSocketDisconnect:
            logger.info("Caller websocket disconnected session=%s", session_id)
            return

    token = set_trace_id(session_state.trace_id)
    logger.info("Streaming bridge accepted session=%s", session_id)
    try:
        async for event in pipeline.handle_stream(
            session_id, audio_stream(), trace_id=session_state.trace_id
        ):
            await websocket.send_json(
                {
                    "event_type": event.event_type.value,
                    "sequence": event.sequence,
                    "session_id": event.session_id,
                    "payload": event.payload,
                    "trace_id": event.trace_id,
                }
            )
    finally:
        reset_trace_id(token)
        await websocket.close()
        logger.info("Streaming bridge closed session=%s", session_id)


@app.get("/v1/calls/{session_id}")
async def session_details(session_id: str) -> JSONResponse:
    session = call_sessions.get(session_id)
    if not session:
        return JSONResponse({"detail": "session not found"}, status_code=404)
    payload = session.payload.model_dump()
    payload["from_number"] = sanitize_value(payload.get("from_number"))
    payload["to_number"] = sanitize_value(payload.get("to_number"))
    payload["trace_id"] = session.trace_id
    return JSONResponse(payload)
