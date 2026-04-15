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
from silero_vad import VADIterator, load_silero_vad

from transcriber import transcribe
from translator import LANGUAGE_NAMES, translate
from tts import synthesize

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
load_dotenv()
# 强制显示所有日志到终端
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    force=True
)
logger = logging.getLogger(__name__)

import uuid

# 全局加载 Silero VAD 模型
vad_model = load_silero_vad()

# 在启动时立即尝试加载模型，不要等点击按钮
from transcriber import _get_model
try:
    _get_model()
except Exception as e:
    logger.error("Failed to preload Whisper model: %s", e)

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
MIN_AUDIO_SECONDS = 0.8
MAX_AUDIO_SECONDS = 8.0  # 降低最大等待时间，防止憋太久
SILENCE_RMS_THRESHOLD = 1500.0  # 提高静音阈值（YouTube的背景音通常大于500），更容易触发断句
SAMPLE_RATE = 16_000  # Whisper native sample rate

def _get_rms(pcm_bytes: bytes) -> float:
    """Calculate the Root Mean Square (energy) of PCM audio."""
    if not pcm_bytes:
        return 0.0
    arr = np.frombuffer(pcm_bytes, dtype=np.int16)
    return float(np.sqrt(np.mean(arr.astype(np.float64)**2)))

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
    logger.info("New WebSocket connection accepted from %s", websocket.client)

    # Per-connection state
    source_lang: str = "en"
    target_lang: str = "zh"
    enable_tts: bool = True
    audio_buffer: deque[bytes] = deque()
    buffered_bytes: int = 0
    
    # 初始化 VAD 迭代器
    # min_silence_duration_ms=800: 指持续静音超过 800ms 才认为一句话说完了。
    # 相比默认的 100ms，增大该值可以获取更长的、完整的句子，极大提高 DeepSeek 的翻译质量和连贯性。
    vad_iterator = VADIterator(
        vad_model, 
        sampling_rate=16000, 
        threshold=0.5, 
        min_silence_duration_ms=800
    )

    # 翻译上下文（保存过去几句的记录，发给 LLM 提供语境，避免代词漏翻错翻）
    chat_context = []

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
                                websocket, pcm, source_lang, target_lang, enable_tts, chat_context
                            )
                        )

            elif "bytes" in message:
                chunk: bytes = message["bytes"]
                audio_buffer.append(chunk)
                buffered_bytes += len(chunk)

                # 将 PCM 字节转换为 float32 数组供 Silero 使用
                chunk_float = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Silero VADIterator 处理 chunk
                # 它会自动检测语谱中的开始(speech_start)和结束(speech_end)
                vad_out = vad_iterator(chunk_float)
                
                current_duration = _pcm_duration(b"".join(audio_buffer))
                
                # 如果检测到说话结束，或者缓冲时间过长(8s)，触发翻译
                if vad_out is not None and "end" in vad_out:
                    logger.info("VAD detected speech end. Duration: %.2fs", current_duration)
                    do_flush = True
                elif current_duration >= MAX_AUDIO_SECONDS:
                    logger.info("Max duration reached. Duration: %.2fs", current_duration)
                    do_flush = True
                else:
                    do_flush = False

                if do_flush:
                    pcm = b"".join(audio_buffer)
                    audio_buffer.clear()
                    buffered_bytes = 0
                    # 注意：VADIterator 内部有状态，触发结束时需要重置状态
                    # 或者我们可以重新实例化一个 vad_iterator (简单粗暴但有效)
                    vad_iterator.reset_states() 
                    
                    asyncio.create_task(
                        _process_audio(
                            websocket, pcm, source_lang, target_lang, enable_tts, chat_context
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
    chat_context: list[dict],
) -> None:
    """Transcribe → translate → (optionally) synthesise, then push to client."""
    try:
        logger.info("Processing %d bytes of audio (%0.2f seconds)...", len(pcm), _pcm_duration(pcm))
        # 1. Speech → Text
        wav_bytes = _bytes_to_wav(pcm)
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            None, transcribe, wav_bytes, source_lang
        )
        if not transcript or len(transcript.strip()) < 2:
            logger.info("No meaningful speech detected (too short).")
            return

        logger.info("Transcript: %s", transcript)

        # 2. Text → Translation (Pass recent context to LLM for perfect accuracy)
        # We pass the last 3 dicts (ID -> src -> dst)
        context_text = ""
        for c in chat_context[-3:]:
             context_text += f"[ID: {c['id']}] Source: {c['source']} | Previous Translation: {c['translation']}\n"
             
        translation_result = await translate(transcript, source_lang, target_lang, context_text)
        translation = translation_result.get("translation", "")
        
        if not translation:
            logger.info("Translation failed or returned empty.")
            await _safe_send(ws, {"type": "transcript", "text": transcript, "lang": source_lang})
            return

        logger.info("Translation: %s", translation)

        # Generate unique ID for this message
        msg_id = uuid.uuid4().hex

        # Filter out invalid corrections
        corrections = translation_result.get("corrections", [])
        
        # Save to context
        chat_context.append({
            "id": msg_id,
            "source": transcript,
            "translation": translation,
        })
        if len(chat_context) > 5:
            chat_context.pop(0)

        # Apply corrections to our own memory so subsequent context isn't using old faulty ones
        for c in corrections:
            for ctx in chat_context:
                if ctx["id"] == c.get("id"):
                    logger.info("Updating memory for ID %s: %s -> %s", ctx["id"], ctx["translation"], c.get("translation"))
                    ctx["translation"] = c.get("translation")

        payload: dict[str, Any] = {
            "type": "translation",
            "id": msg_id,
            "text": translation,
            "lang": target_lang,
            "source_text": transcript,
            "updates": corrections
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
