"""
Word data service backed by OpenAI o4-mini.

Single public function fetch_full_quiz_package(lang):
  One API call returns the word + all its linguistic data + a pool of
  up to 5 quiz variations.  The pool is stored in the DB so watering
  never needs to call OpenAI again.
"""

import json
import random
import re
from typing import Optional
from openai import AsyncOpenAI
from config import get_settings

settings = get_settings()
_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


LANG_INFO = {
    "english":    {"name": "English",    "color": "#5a9eb8"},
    "vietnamese": {"name": "Vietnamese", "color": "#d4267a"},
    "japanese":   {"name": "Japanese",   "color": "#c1325a"},
    "chinese":    {"name": "Chinese",    "color": "#d97a3e"},
    "french":     {"name": "French",     "color": "#2176c7"},
    "german":     {"name": "German",     "color": "#5a3e8e"},
    "spanish":    {"name": "Spanish",    "color": "#5a9333"},
}

_SEED_TOPICS = [
    "nature", "food", "emotion", "science", "music", "architecture",
    "geography", "sport", "technology", "philosophy", "medicine", "art",
    "mythology", "law", "economics", "literature", "astronomy", "cooking",
]

_PROMPT = """\
Choose a real {lang_name} word related to the topic '{topic}'. Prefer everyday words \
that a learner would encounter in daily life, news, or conversation. \
Avoid rare, archaic, or highly technical words.

Return a single JSON object with EXACTLY these keys:

"word"             : the chosen {lang_name} word (written in its native script)
"ipa"              : IPA pronunciation e.g. /wɜːrd/, or null
"gloss"            : concise one-sentence English definition
"part_of_speech"   : noun | verb | adjective | adverb | etc., or null
"example_sentence" : a short natural {lang_name} sentence using the word (or any \
inflection) replaced by ___, or null if unnatural
"quizzes"          : array of EXACTLY 5 quiz objects using the following types \
(vary the types; you may repeat a type with different distractors if needed):

  {{ "type": "meaning",
     "correct": <the English gloss above>,
     "distractors": [3 plausible but wrong English one-sentence definitions] }}

  {{ "type": "fill_blank",
     "question": <example_sentence in {lang_name} with ___ blank>,
     "correct": <the {lang_name} word>,
     "distractors": [3 real {lang_name} words that could plausibly but wrongly fill the blank] }}

  {{ "type": "synonym",
     "correct": <a common {lang_name} synonym>,
     "distractors": [3 {lang_name} words that are NOT synonyms] }}

  {{ "type": "antonym",
     "correct": <a common {lang_name} antonym>,
     "distractors": [3 {lang_name} words that are NOT antonyms] }}

Rules:
- Produce exactly 5 quiz objects. If a type (e.g. antonym) doesn't apply, \
use a different type instead — never produce fewer than 5.
- All distractor arrays must have exactly 3 items.
- Return ONLY valid JSON. No markdown fences. No extra text.
"""


def _parse_json(raw: str, label: str, finish_reason: str = "") -> Optional[dict]:
    if not raw:
        print(f"[openai] empty response for {label!r} (finish={finish_reason!r})")
        return None
    cleaned = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        print(f"[openai] JSON parse error for {label!r} (finish={finish_reason!r}): {raw[:200]!r}")
        return None


async def fetch_full_quiz_package(lang: str = "english") -> Optional[dict]:
    """
    One API call → word data + quiz pool (5 variations).
    lang: one of the keys in LANG_INFO (defaults to "english").
    Returns None if the call fails or produces an unusable word.
    """
    info = LANG_INFO.get(lang, LANG_INFO["english"])
    lang_name = info["name"]
    topic = random.choice(_SEED_TOPICS)

    resp = await _get_client().chat.completions.create(
        model="o4-mini",
        messages=[{"role": "user", "content": _PROMPT.format(lang_name=lang_name, topic=topic)}],
        max_completion_tokens=4000,
        reasoning_effort="low",
    )
    choice = resp.choices[0]
    raw = (choice.message.content or "").strip()
    data = _parse_json(raw, f"<random-{lang}>", choice.finish_reason)
    if not data:
        return None

    word = (data.get("word") or "").strip()
    if not word or not data.get("gloss"):
        return None

    quizzes = []
    for q in (data.get("quizzes") or []):
        qtype = q.get("type")
        correct = (q.get("correct") or "").strip()
        distractors = [str(x).strip() for x in (q.get("distractors") or []) if x][:3]
        if not qtype or not correct or len(distractors) < 3:
            continue
        entry = {"type": qtype, "correct": correct, "distractors": distractors}
        if qtype == "fill_blank":
            q_text = (q.get("question") or "").strip()
            if "___" not in q_text:
                continue
            entry["question"] = q_text
        quizzes.append(entry)

    pkg = {
        "word":             word,
        "lang":             lang_name,
        "lang_color":       info["color"],
        "ipa":              (data.get("ipa") or "").strip("/") or None,
        "gloss":            data.get("gloss"),
        "part_of_speech":   data.get("part_of_speech") or None,
        "example_sentence": None,
        "quizzes":          quizzes,
    }
    ex = (data.get("example_sentence") or "").strip()
    if "___" in ex:
        pkg["example_sentence"] = ex

    print(f"[openai] lang={lang_name!r} word={word!r} quizzes={[q['type'] for q in quizzes]}")
    return pkg if quizzes else None
