"""
Text-to-speech via YarnGPT API.
Generates a Nigerian-accented pronunciation of a word or phrase.
Returns raw audio bytes in opus format, ready to send as a Telegram voice note.
"""

import re
import logging
import requests
from src.config import YARNGPT_API_KEY, YARNGPT_VOICE

logger = logging.getLogger(__name__)

YARNGPT_API_URL = "https://yarngpt.ai/api/v1/tts"
TIMEOUT_SECONDS = 60

# Common question prefixes users might send
_QUESTION_PREFIXES = re.compile(
    r"^(what'?s\s+a[n]?\s+|what\s+is\s+a[n]?\s+|define\s+|meaning\s+of\s+|explain\s+)",
    re.IGNORECASE,
)


def extract_word(text: str) -> str:
    """
    Strip question prefixes so we only pass the core word/phrase to TTS.
    e.g. "what's a subnet" -> "subnet"
         "define ephemeral" -> "ephemeral"
         "volatile"         -> "volatile"
    """
    cleaned = _QUESTION_PREFIXES.sub("", text.strip())
    return cleaned.strip()


def generate_pronunciation(word: str) -> bytes | None:
    """
    Call YarnGPT and return opus audio bytes for the given word.
    Returns None if the call fails — caller should handle gracefully.
    """
    core_word = extract_word(word)
    text = _build_pronunciation_text(core_word)
    payload = {
        "text": text,
        "voice": YARNGPT_VOICE,
        "response_format": "opus",
    }

    logger.info(f"[YarnGPT] Requesting pronunciation for '{core_word}' (input: '{word}')")

    try:
        response = requests.post(
            YARNGPT_API_URL,
            headers={
                "Authorization": f"Bearer {YARNGPT_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=TIMEOUT_SECONDS,
            stream=True,
        )

        logger.info(f"[YarnGPT] Response status: {response.status_code}")

        if response.status_code == 200:
            audio = response.content
            logger.info(f"[YarnGPT] Audio received: {len(audio)} bytes")
            return audio
        else:
            logger.error(
                f"[YarnGPT] API error {response.status_code}: {response.text[:300]}"
            )
            return None

    except requests.exceptions.Timeout:
        logger.error(f"[YarnGPT] Request timed out after {TIMEOUT_SECONDS}s for word '{core_word}'")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[YarnGPT] Connection error - cannot reach {YARNGPT_API_URL}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"[YarnGPT] Request failed: {type(e).__name__}: {e}")
        return None


def _build_pronunciation_text(word: str) -> str:
    """
    Saying the word twice helps with retention.
    """
    return f"Let me pronounce that for you. {word}. {word}."