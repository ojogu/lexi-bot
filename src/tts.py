"""
Text-to-speech via ElevenLabs SDK.
Generates natural-sounding pronunciation of a word or phrase.
Returns raw audio bytes in mp3 format, ready to send as a Telegram voice note.
"""

import re
import logging
from elevenlabs.client import ElevenLabs
from src.config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

logger = logging.getLogger(__name__)

_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# Common question prefixes to strip before passing to TTS
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
    Call ElevenLabs and return mp3 audio bytes for the given word.
    Returns None if the call fails — caller handles gracefully.
    """
    core_word = extract_word(word)
    text = f"Let me pronounce that for you. {core_word}. {core_word}."

    logger.info(f"[ElevenLabs] Requesting pronunciation for '{core_word}' (input: '{word}')")

    try:
        audio = _client.text_to_speech.convert(
            text=text,
            voice_id=ELEVENLABS_VOICE_ID,
            model_id="eleven_flash_v2_5",  # lowest latency model
            output_format="mp3_44100_128",
        )

        # SDK returns a generator — collect all chunks into bytes
        audio_bytes = b"".join(audio)
        logger.info(f"[ElevenLabs] Audio received: {len(audio_bytes)} bytes")
        return audio_bytes

    except Exception as e:
        logger.error(f"[ElevenLabs] Request failed: {type(e).__name__}: {e}")
        return None