"""Streaming telephony pipeline wiring STT -> LLM -> TTS."""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import struct
import time
from collections import deque
from typing import AsyncIterable, AsyncIterator, Iterable, List

from shared.observability import reset_trace_id, set_trace_id
from shared.streaming import (
    AudioChunk,
    LLMResponseChunk,
    StreamEvent,
    StreamEventType,
    TranscriptChunk,
    TTSChunk,
)

DEFAULT_SAMPLE_RATE = 16000


class DummySpeechToText:
    """Toy speech-to-text engine that maps audio frames to scripted transcripts."""

    def __init__(self, scripted_transcript: Iterable[str] | None = None) -> None:
        self._script = deque(scripted_transcript or ["Hello there", "I'd like to book a meeting", "Thank you"])

    async def stream(self, audio_frames: AsyncIterable[AudioChunk]) -> AsyncIterator[TranscriptChunk]:
        sequence = 0
        async for _frame in audio_frames:
            text = self._next_text()
            yield TranscriptChunk(
                session_id=_frame.session_id,
                sequence=sequence,
                text=text,
                is_final=True,
            )
            sequence += 1
            await asyncio.sleep(0)

    def _next_text(self) -> str:
        text = self._script.popleft()
        self._script.append(text)
        return text


class DummyLLM:
    """Simple conversational model that reflects transcript text."""

    def __init__(self, system_prompt: str | None = None) -> None:
        self._system_prompt = system_prompt or "You are a helpful voice assistant."

    async def stream(self, transcripts: AsyncIterable[TranscriptChunk]) -> AsyncIterator[LLMResponseChunk]:
        async for chunk in transcripts:
            text = f"{self._system_prompt} Caller said: {chunk.text}."
            yield LLMResponseChunk(
                session_id=chunk.session_id,
                sequence=chunk.sequence,
                text=text,
                is_final=chunk.is_final,
            )
            await asyncio.sleep(0)


class DummyTextToSpeech:
    """Tone-based synthesizer that renders ASCII text to audio frames."""

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate

    async def stream(self, responses: AsyncIterable[LLMResponseChunk]) -> AsyncIterator[TTSChunk]:
        async for chunk in responses:
            payload = self._tone_for_text(chunk.text)
            yield TTSChunk(
                session_id=chunk.session_id,
                sequence=chunk.sequence,
                sample_rate=self.sample_rate,
                payload=payload,
                is_final=chunk.is_final,
            )
            await asyncio.sleep(0)

    def _tone_for_text(self, text: str) -> bytes:
        duration = 0.35
        frames = int(duration * self.sample_rate)
        amplitude = 16000
        base_frequency = 440
        frequency = base_frequency + (len(text) % 12) * 20
        waveform = bytearray()
        for i in range(frames):
            sample = int(amplitude * math.sin(2 * math.pi * frequency * (i / self.sample_rate)))
            waveform.extend(struct.pack("<h", sample))
        return bytes(waveform)


class StreamingPipeline:
    """Coordinates the STT -> LLM -> TTS flow for a call session."""

    def __init__(
        self,
        stt: DummySpeechToText | None = None,
        llm: DummyLLM | None = None,
        tts: DummyTextToSpeech | None = None,
    ) -> None:
        self.stt = stt or DummySpeechToText()
        self.llm = llm or DummyLLM()
        self.tts = tts or DummyTextToSpeech()

    async def handle_stream(
        self,
        session_id: str,
        audio_frames: AsyncIterable[AudioChunk],
        *,
        trace_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        token = set_trace_id(trace_id) if trace_id else None
        start = time.perf_counter()
        first_response_logged = False
        try:
            async for transcript in self.stt.stream(audio_frames):
                LOGGER.info(
                    "STT transcript session=%s seq=%s final=%s",
                    session_id,
                    transcript.sequence,
                    transcript.is_final,
                )
                yield StreamEvent(
                    event_type=StreamEventType.TRANSCRIPT,
                    sequence=transcript.sequence,
                    session_id=session_id,
                    payload={"text": transcript.text, "is_final": transcript.is_final},
                    trace_id=trace_id,
                )

                async for response in self.llm.stream(_single(transcript)):
                    if not first_response_logged:
                        latency_ms = (time.perf_counter() - start) * 1000
                        LOGGER.info(
                            "First response ready session=%s latency=%.2fms",
                            session_id,
                            latency_ms,
                        )
                        first_response_logged = True
                    LOGGER.info(
                        "LLM response session=%s seq=%s final=%s",
                        session_id,
                        response.sequence,
                        response.is_final,
                    )
                    yield StreamEvent(
                        event_type=StreamEventType.LLM_RESPONSE,
                        sequence=response.sequence,
                        session_id=session_id,
                        payload={"text": response.text, "is_final": response.is_final},
                        trace_id=trace_id,
                    )

                    async for synthesized in self.tts.stream(_single(response)):
                        LOGGER.info(
                            "TTS chunk session=%s seq=%s final=%s",
                            session_id,
                            synthesized.sequence,
                            synthesized.is_final,
                        )
                        yield StreamEvent(
                            event_type=StreamEventType.AUDIO_OUT,
                            sequence=synthesized.sequence,
                            session_id=session_id,
                            payload={
                                "sample_rate": synthesized.sample_rate,
                                "audio_base64": base64.b64encode(
                                    synthesized.payload
                                ).decode("ascii"),
                                "is_final": synthesized.is_final,
                            },
                            trace_id=trace_id,
                        )
        finally:
            if token is not None:
                reset_trace_id(token)

    async def collect_audio_events(self, events: AsyncIterable[StreamEvent]) -> List[TTSChunk]:
        collected: List[TTSChunk] = []
        async for event in events:
            if event.event_type == StreamEventType.AUDIO_OUT:
                payload = event.payload
                collected.append(
                    TTSChunk(
                        session_id=event.session_id,
                        sequence=event.sequence,
                        sample_rate=payload["sample_rate"],
                        payload=base64.b64decode(payload["audio_base64"]),
                        is_final=payload.get("is_final", False),
                        trace_id=event.trace_id,
                    )
                )
        return collected


def _single(item):
    async def iterator():
        yield item

    return iterator()


async def chunk_wav(  # pragma: no cover - simple utility exercised through harness
    session_id: str,
    wav_reader,
    chunk_duration: float = 0.5,
) -> AsyncIterator[AudioChunk]:
    sample_rate = wav_reader.getframerate()
    frames_per_chunk = int(sample_rate * chunk_duration)
    sequence = 0
    while True:
        data = wav_reader.readframes(frames_per_chunk)
        if not data:
            break
        yield AudioChunk(
            session_id=session_id,
            sequence=sequence,
            sample_rate=sample_rate,
            payload=data,
        )
        sequence += 1
        await asyncio.sleep(0)
LOGGER = logging.getLogger("telephony.pipeline")
