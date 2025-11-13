"""Local test harness to simulate inbound calls over the streaming pipeline."""

from __future__ import annotations

import argparse
import argparse
import asyncio
import base64
import io
import math
import struct
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import wave

# Add shared modules to sys.path for local execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

try:  # pragma: no cover - optional runtime dependency
    import simpleaudio as sa
except ImportError:  # pragma: no cover - fallback when playback is unavailable
    sa = None

from shared.leads import LeadStore
from shared.observability import configure_logging, generate_trace_id, reset_trace_id, set_trace_id
from shared.streaming import StreamEventType
from pipeline import StreamingPipeline, chunk_wav


lead_store = LeadStore()
configure_logging("telephony-harness")


async def stream_call(sample_path: Path | None) -> None:
    pipeline = StreamingPipeline()
    session_id = "local-test"
    trace_id = generate_trace_id()
    transcripts: list[str] = []
    started = datetime.utcnow()

    with open_wav_source(sample_path) as wav_reader:
        events = pipeline.handle_stream(
            session_id,
            chunk_wav(session_id, wav_reader),
            trace_id=trace_id,
        )
        token = set_trace_id(trace_id)
        try:
            async for event in events:
                if event.event_type == StreamEventType.TRANSCRIPT:
                    print(f"[Transcript][{event.trace_id}] {event.payload['text']}")
                    transcripts.append(event.payload["text"])
                elif event.event_type == StreamEventType.LLM_RESPONSE:
                    print(f"[LLM][{event.trace_id}] {event.payload['text']}")
                elif event.event_type == StreamEventType.AUDIO_OUT:
                    raw_audio = decode_audio(event.payload["audio_base64"])
                    if sa is not None:
                        play_audio(raw_audio, event.payload["sample_rate"])
                    else:
                        print(
                            "[Audio][{trace}] chunk ready (install simpleaudio for playback)".format(
                                trace=event.trace_id
                            )
                        )
        finally:
            reset_trace_id(token)

    await log_lead(session_id, transcripts, started)


def decode_audio(encoded: str | bytes) -> bytes:
    if isinstance(encoded, str):
        encoded = encoded.encode("ascii")
    return base64.b64decode(encoded)


def play_audio(raw_audio: bytes, sample_rate: int) -> None:
    if sa is None:
        return
    wave_obj = sa.WaveObject(raw_audio, 1, 2, sample_rate)
    play_obj = wave_obj.play()
    play_obj.wait_done()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate a test call streaming session")
    parser.add_argument(
        "--sample",
        type=Path,
        default=None,
        help="Optional path to a WAV file representing the inbound caller audio",
    )
    return parser.parse_args()


async def log_lead(session_id: str, transcripts: list[str], started: datetime) -> None:
    if not transcripts:
        print("[Lead] No transcripts captured; skipping lead logging.")
        return

    ended = datetime.utcnow()
    transcript_text = "\n".join(transcripts)
    summary = transcripts[-1]

    lead = lead_store.create_lead(
        caller_name="Test Caller",
        caller_phone="555-0162",
        caller_email="caller@example.com",
        transcript=transcript_text,
        summary=summary,
    )
    lead_store.record_call(
        lead["id"],
        call_sid=session_id,
        direction="inbound",
        started_at=started,
        ended_at=ended,
        duration_seconds=int((ended - started).total_seconds()),
        transcript=transcript_text,
        summary=summary,
    )
    print(
        "[Lead] Stored lead #{lead_id} with summary: {summary}".format(
            lead_id=lead["id"], summary=summary
        )
    )


def main() -> None:
    args = parse_args()
    asyncio.run(stream_call(args.sample))


if __name__ == "__main__":
    main()


@contextmanager
def open_wav_source(sample_path: Path | None):
    """Open a WAV reader either from disk or a generated synthetic sample."""

    buffer: io.BytesIO | None = None
    if sample_path is not None:
        if not sample_path.exists():
            raise FileNotFoundError(f"Sample file not found: {sample_path}")
        wav_handle = wave.open(str(sample_path), "rb")
    else:
        buffer = generate_dummy_wav()
        wav_handle = wave.open(buffer, "rb")

    try:
        yield wav_handle
    finally:
        wav_handle.close()
        if buffer is not None:
            buffer.close()


def generate_dummy_wav(
    duration_seconds: float = 3.0,
    sample_rate: int = 16000,
    base_frequency: float = 220.0,
) -> io.BytesIO:
    """Create a simple sine wave WAV stream for local harness testing."""

    total_frames = int(duration_seconds * sample_rate)
    amplitude = 16000
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_writer:
        wav_writer.setnchannels(1)
        wav_writer.setsampwidth(2)
        wav_writer.setframerate(sample_rate)
        for index in range(total_frames):
            sample = int(
                amplitude
                * math.sin(2 * math.pi * base_frequency * (index / sample_rate))
            )
            wav_writer.writeframes(struct.pack("<h", sample))
    buffer.seek(0)
    return buffer
