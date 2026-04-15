"""
translator.py – LLM-powered translation via an OpenAI-compatible API.
"""
from __future__ import annotations

import logging
import os

import json
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


async def translate(text: str, source_lang: str, target_lang: str, context: str = "") -> dict:
    """
    Translate *text* from *source_lang* to *target_lang* using the configured
    LLM.  Includes previous *context* sentences for improved accuracy (avoiding
    lost pronouns, missed objects, etc.)
    Returns a dict with 'translation' and optionally 'corrections'.
    """
    if not text.strip():
        return {"translation": ""}

    src_name = LANGUAGE_NAMES.get(source_lang, source_lang)
    tgt_name = LANGUAGE_NAMES.get(target_lang, target_lang)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    system_prompt = (
        f"You are a professional real-time {src_name} to {tgt_name} interpreter.\n"
        f"Your task is to provide the BEST translation based on the context.\n"
        f"You must strictly output a valid JSON object matching this schema:\n"
        f"{{\n"
        f"  \"translation\": \"<translate the new User message here>\",\n"
        f"  \"corrections\": [\n"
        f"       {{\"id\": \"<provide the id from context>\", \"translation\": \"<provide corrected translation if you realized the previous is wrong, otherwise empty array>\"}}\n"
        f"  ]\n"
        f"}}\n"
        f"Output ONLY JSON."
    )
    if context:
        system_prompt += f"\n\nHere is the previous context and their IDs (Do NOT translate this, use it to understand pronouns and context, AND correct them if they were wrong):\n{context}"

    try:
        response = await _client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1024,
        )
        content = response.choices[0].message.content or ""
        # Strip potential markdown formatting
        if content.startswith("```"):
            lines = content.strip().split("\n")
            if lines[0].startswith("```"): lines = lines[1:]
            if lines[-1].startswith("```"): lines = lines[:-1]
            content = "\n".join(lines).strip()

        data = json.loads(content)
        translated = data.get("translation", "").strip()
        logger.debug("Translated (%s→%s): %r → %r (Corrections: %s)", source_lang, target_lang, text, translated, data.get("corrections"))
        return data
    except Exception as e:
        logger.error("JSON parsing or API error in translation: %s", e)
        # Fallback empty
        return {"translation": ""}
