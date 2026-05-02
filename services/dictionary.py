"""
Word data service — dispatches to either:
  - "external"  API-Ninjas (random word) + Free Dictionary API (definition)
  - "openai"    OpenAI o4-mini for both random word and definition

Controlled by WORD_SERVICE=external|openai in .env (default: external).
"""

import re
import httpx
from config import get_settings

settings = get_settings()

NINJAS_URL    = "https://api.api-ninjas.com/v2/randomword"
FREE_DICT_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"


# ── External API implementations ─────────────────────────────────────────────

async def _fetch_random_word_external() -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            NINJAS_URL,
            headers={"X-Api-Key": settings.api_ninjas_key},
        )
        response.raise_for_status()
        data = response.json()
        print(f"[ninjas] {data}")
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        raise ValueError(f"Unexpected response from API-Ninjas: {data}")


async def _fetch_definition_external(word: str) -> dict:
    result = {"ipa": None, "gloss": None, "part_of_speech": None, "example_sentence": None}
    url = FREE_DICT_URL.format(word=word)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)

    if response.status_code != 200:
        print(f"[dict] {word!r} → {response.status_code}")
        return result

    try:
        data = response.json()
    except Exception:
        print(f"[dict] {word!r} → non-JSON response")
        return result

    if not data or not isinstance(data, list):
        return result

    entry = data[0]

    for ph in entry.get("phonetics", []):
        if ph.get("text"):
            result["ipa"] = ph["text"]
            break

    for meaning in entry.get("meanings", []):
        pos = meaning.get("partOfSpeech", "")
        for defn in meaning.get("definitions", []):
            definition = defn.get("definition", "")
            if not definition:
                continue
            if not result["gloss"]:
                result["gloss"] = definition
                result["part_of_speech"] = pos
            example = defn.get("example", "")
            if example and not result["example_sentence"]:
                blank = _make_blank(example, word)
                if blank:
                    result["example_sentence"] = blank
            if result["gloss"] and result["example_sentence"]:
                break
        if result["gloss"] and result["example_sentence"]:
            break

    print(f"[dict] {word!r} → gloss={result['gloss']!r}  ex={result['example_sentence']!r}")
    return result


def _make_blank(sentence: str, word: str) -> str:
    pattern = re.compile(re.escape(word) + r"(?:ing|ed|s|er|est|ly)?", re.IGNORECASE)
    blanked = pattern.sub("___", sentence, count=1)
    return blanked if "___" in blanked else ""


# ── Public API — delegates based on WORD_SERVICE ─────────────────────────────

async def fetch_random_word() -> str:
    """External mode only — returns a single random word string."""
    return await _fetch_random_word_external()


async def fetch_definition(word: str) -> dict:
    """External mode only — returns definition dict for a given word."""
    return await _fetch_definition_external(word)


async def fetch_full_quiz_package(
    lang: str = "english",
    vocab_level=None,
    topic_prefs=None,
    definition_lang: str = "english",
    exclude_words=None,
):
    """
    OpenAI mode: one call → word + definition + quiz pool (3-4 types).
    Returns None if the call fails or produces an unusable word.
    """
    from services.openai_dictionary import fetch_full_quiz_package as _openai_pkg
    return await _openai_pkg(
        lang=lang,
        vocab_level=vocab_level,
        topic_prefs=topic_prefs,
        definition_lang=definition_lang,
        exclude_words=exclude_words,
    )
