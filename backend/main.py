"""
main.py – FastAPI application entry-point.

Architecture
────────────
WebSocket /ws/translate
  Client → sends JSON control messages OR raw binary audio chunks.
  Server → sends JSON messages with transcription, translation, and (optionally)
            a base64-encoded MP3 TTS audio payload.

REST
  GET  /health        – liveness probe
  GET  /languages     – list supported language pairs
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
from collections import deque
from typing import Any

import numpy as np
import soundfile as sf
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from transcriber import transcribe
from translator import LANGUAGE_NAMES, translate
from tts import synthesize

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Realtime Translator", version="1.0.0")

origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/languages")
async def languages() -> dict[str, Any]:
    return {"languages": LANGUAGE_NAMES}


# ---------------------------------------------------------------------------
# WebSocket helpers
# ---------------------------------------------------------------------------

# Buffer ≥ MIN_AUDIO_SECONDS before sending to Whisper (reduces hallucinations
# on very short clips).
MIN_AUDIO_SECONDS = 1.5
SAMPLE_RATE = 16_000  # Whisper native sample rate


def _pcm_duration(pcm_bytes: bytes) -> float:
    """Return duration in seconds of raw int16 mono 16 kHz PCM."""
    return len(pcm_bytes) / 2 / SAMPLE_RATE


def _bytes_to_wav(pcm_bytes: bytes) -> bytes:
    """Wrap raw int16 mono 16 kHz PCM in a WAV container."""
    buf = io.BytesIO()
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


async def _safe_send(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws/translate")
async def ws_translate(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("WebSocket connected: %s", websocket.client)

    # Per-connection state
    source_lang: str = "en"
    target_lang: str = "zh"
    enable_tts: bool = True
    audio_buffer: deque[bytes] = deque()
    buffered_bytes: int = 0

    try:
        while True:
            message = await websocket.receive()

            # ── Control / config message (JSON text) ──────────────────────
            if "text" in message:
                try:
                    data: dict = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type", "")

                if msg_type == "config":
                    source_lang = data.get("source_lang", source_lang)
                    target_lang = data.get("target_lang", target_lang)
                    enable_tts = data.get("enable_tts", enable_tts)
                    await _safe_send(
                        websocket,
                        {
                            "type": "config_ack",
                            "source_lang": source_lang,
                            "target_lang": target_lang,
                            "enable_tts": enable_tts,
                        },
                    )

                elif msg_type == "flush":
                    # Client explicitly requests processing of buffered audio
                    if buffered_bytes > 0:
                        pcm = b"".join(audio_buffer)
                        audio_buffer.clear()
                        buffered_bytes = 0
                        asyncio.create_task(
                            _process_audio(
                                websocket, pcm, source_lang, target_lang, enable_tts
                            )
                        )

            # ── Audio chunk (binary) ──────────────────────────────────────
            elif "bytes" in message:
                chunk: bytes = message["bytes"]
                audio_buffer.append(chunk)
                buffered_bytes += len(chunk)

                if _pcm_duration(b"".join(audio_buffer)) >= MIN_AUDIO_SECONDS:
                    pcm = b"".join(audio_buffer)
                    audio_buffer.clear()
                    buffered_bytes = 0
                    asyncio.create_task(
                        _process_audio(
                            websocket, pcm, source_lang, target_lang, enable_tts
                        )
                    )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", websocket.client)
    except Exception as exc:
        logger.exception("Unexpected WebSocket error: %s", exc)
        await _safe_send(websocket, {"type": "error", "message": str(exc)})


async def _process_audio(
    ws: WebSocket,
    pcm: bytes,
    source_lang: str,
    target_lang: str,
    enable_tts: bool,
) -> None:
    """Transcribe → translate → (optionally) synthesise, then push to client."""
    try:
        # 1. Speech → Text
        wav_bytes = _bytes_to_wav(pcm)
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            None, transcribe, wav_bytes, source_lang
        )
        if not transcript:
            return

        await _safe_send(ws, {"type": "transcript", "text": transcript, "lang": source_lang})

        # 2. Text → Translation
        translation = await translate(transcript, source_lang, target_lang)
        if not translation:
            return

        payload: dict[str, Any] = {
            "type": "translation",
            "text": translation,
            "lang": target_lang,
            "source_text": transcript,
        }

        # 3. Translation → Speech (TTS)
        if enable_tts:
            audio_bytes = await synthesize(translation, target_lang)
            if audio_bytes:
                payload["audio"] = base64.b64encode(audio_bytes).decode()
                payload["audio_format"] = "mp3"

        await _safe_send(ws, payload)

    except Exception as exc:
        logger.exception("Error processing audio: %s", exc)
        await _safe_send(ws, {"type": "error", "message": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
