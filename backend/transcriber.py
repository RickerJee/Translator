"""
transcriber.py – Faster-Whisper speech-to-text wrapper.
"""
from __future__ import annotations

import io
import logging
import os

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton so the heavy model is loaded only once.
# ---------------------------------------------------------------------------
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        model_size = os.getenv("WHISPER_MODEL", "base")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        logger.info("Loading Whisper model '%s' on %s …", model_size, device)
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("Whisper model loaded.")
    return _model


def transcribe(audio_bytes: bytes, language: str | None = None) -> str:
    """
    Transcribe raw audio bytes (any format supported by soundfile / ffmpeg)
    and return the plain-text transcript.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio data (PCM WAV, WebM, Opus, …).
    language : str | None
        BCP-47 language code hint, e.g. ``"en"`` or ``"zh"``.
        Pass *None* to let Whisper auto-detect.

    Returns
    -------
    str
        Concatenated transcript text.
    """
    model = _get_model()

    # Convert raw bytes → float32 numpy array via soundfile.
    try:
        audio_array, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    except Exception as exc:
        logger.warning("soundfile could not decode audio (%s); trying raw PCM 16-bit.", exc)
        # Fall back: assume 16-bit PCM mono @ 16 kHz.
        # Divide by 32768 (2^15) to normalize int16 range [-32768, 32767] → float32 [-1.0, 1.0].
        audio_array = (
            np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        )

    # Faster-Whisper expects mono audio.
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    kwargs: dict = dict(beam_size=5)
    if language:
        kwargs["language"] = language

    segments, _info = model.transcribe(audio_array, **kwargs)
    return " ".join(seg.text.strip() for seg in segments).strip()
