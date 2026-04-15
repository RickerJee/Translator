"""
tts.py – Azure Cognitive Services Text-to-Speech helper.

Falls back to a plain error string when Azure credentials are missing so that
the rest of the app keeps working in demo / development mode.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Voice map: BCP-47 language tag → Azure Neural voice name
VOICE_MAP: dict[str, str] = {
    "en": "en-US-JennyNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "zh-tw": "zh-TW-HsiaoChenNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ar": "ar-EG-SalmaNeural",
    "hi": "hi-IN-SwaraNeural",
    "it": "it-IT-ElsaNeural",
    "nl": "nl-NL-ColetteNeural",
    "pl": "pl-PL-ZofiaNeural",
    "tr": "tr-TR-EmelNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "th": "th-TH-PremwadeeNeural",
}


async def synthesize(text: str, language: str) -> bytes | None:
    """
    Synthesize *text* to speech using Azure TTS.

    Returns raw MP3 audio bytes, or *None* if synthesis could not be
    completed (e.g. missing credentials).
    """
    speech_key = os.getenv("AZURE_SPEECH_KEY", "")
    speech_region = os.getenv("AZURE_SPEECH_REGION", "eastus")

    if not speech_key:
        logger.warning("AZURE_SPEECH_KEY not set – TTS disabled.")
        return None

    try:
        import azure.cognitiveservices.speech as speechsdk  # noqa: PLC0415
    except ImportError:
        logger.warning("azure-cognitiveservices-speech not installed – TTS disabled.")
        return None

    voice = VOICE_MAP.get(language, "en-US-JennyNeural")

    speech_config = speechsdk.SpeechConfig(
        subscription=speech_key, region=speech_region
    )
    speech_config.speech_synthesis_voice_name = voice
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
    )

    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=None
    )
    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return bytes(result.audio_data)

    logger.error("Azure TTS failed: %s", result.cancellation_details)
    return None
