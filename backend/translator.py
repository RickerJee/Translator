"""
translator.py – LLM-powered translation via an OpenAI-compatible API.
"""
from __future__ import annotations

import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language display names used in the system prompt.
# ---------------------------------------------------------------------------
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "zh": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "hi": "Hindi",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
}


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


async def translate(text: str, source_lang: str, target_lang: str) -> str:
    """
    Translate *text* from *source_lang* to *target_lang* using the configured
    LLM.  Returns the translated string.
    """
    if not text.strip():
        return ""

    src_name = LANGUAGE_NAMES.get(source_lang, source_lang)
    tgt_name = LANGUAGE_NAMES.get(target_lang, target_lang)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    system_prompt = (
        f"You are a professional real-time interpreter. "
        f"Translate the following {src_name} text into {tgt_name}. "
        f"Output ONLY the translation, no explanations, no extra text."
    )

    response = await _client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        temperature=0.2,
        max_tokens=1024,
    )
    translated = response.choices[0].message.content or ""
    logger.debug("Translated (%s→%s): %r → %r", source_lang, target_lang, text, translated)
    return translated.strip()
