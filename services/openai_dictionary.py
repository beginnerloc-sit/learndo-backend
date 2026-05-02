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

_LEVEL_GUIDANCE = {
    "beginner":     "Choose a SIMPLE everyday word that a beginner learner would encounter in their first months of study.",
    "intermediate": "Choose a moderately common word that an intermediate learner would encounter in daily conversation, news, or media.",
    "advanced":     "Choose a more nuanced, less common word — but still a real word a fluent speaker would actually use.",
}

_PROMPT = """\
{level_line} The word should relate to the topic '{topic}' if natural, otherwise pick \
a thematically adjacent word.{exclude_line}

Return a single JSON object with EXACTLY these keys:

"word"             : the chosen {lang_name} word (written in its native script)
"ipa"              : IPA pronunciation e.g. /wɜːrd/, or null
"gloss"            : concise one-sentence definition WRITTEN IN {def_lang_name}
"part_of_speech"   : noun | verb | adjective | adverb | etc., or null
"example_sentence" : a short natural {lang_name} sentence using the word (or any \
inflection) replaced by ___, or null if unnatural
"quizzes"          : array of EXACTLY 5 quiz objects using the following types \
(vary the types; you may repeat a type with different distractors if needed):

  {{ "type": "meaning",
     "correct": <the {def_lang_name} gloss above>,
     "distractors": [3 plausible but wrong one-sentence definitions in {def_lang_name}] }}

  {{ "type": "rearrange",
     "correct_tokens": [<ordered list of 4-8 tokens — words/particles — that, when joined with single spaces, form a natural {lang_name} sentence that USES the target word; tokenize at the natural word boundary level for the language (single space-separated words for Latin scripts; logical word/particle units for Japanese/Chinese)>],
     "sentence_meaning": <a natural translation of the full sentence written in {def_lang_name} — this is shown to the player as a hint for what sentence they need to build>,
     "distractors": [3 plausible {lang_name} word/particle distractors that DON'T belong in this sentence and would not form a valid sentence if used] }}

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
- Definitions/meanings/distractors for "meaning" and "fill_blank" types MUST be written in {def_lang_name}.
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


async def fetch_full_quiz_package(
    lang: str = "english",
    vocab_level: Optional[str] = None,
    topic_prefs: Optional[list] = None,
    definition_lang: str = "english",
    exclude_words: Optional[list] = None,
) -> Optional[dict]:
    """
    One API call → word data + quiz pool (5 variations).
    lang:           target language to study (key of LANG_INFO).
    vocab_level:    "beginner" | "intermediate" | "advanced" (controls difficulty).
    topic_prefs:    optional list of topic strings — picks one randomly. Falls back to global pool.
    definition_lang: language to write definitions/meanings in (key of LANG_INFO).
    Returns None if the call fails or produces an unusable word.
    """
    info = LANG_INFO.get(lang, LANG_INFO["english"])
    lang_name = info["name"]
    def_info = LANG_INFO.get(definition_lang, LANG_INFO["english"])
    def_lang_name = def_info["name"]

    pool = topic_prefs if topic_prefs else _SEED_TOPICS
    topic = random.choice(pool)
    level_line = _LEVEL_GUIDANCE.get(vocab_level or "intermediate", _LEVEL_GUIDANCE["intermediate"]).format(lang_name=lang_name)
    if "{lang_name}" not in level_line:
        level_line = level_line.replace("a beginner learner", f"a beginner {lang_name} learner") \
                               .replace("an intermediate learner", f"an intermediate {lang_name} learner") \
                               .replace("a fluent speaker", f"a fluent {lang_name} speaker")

    exclude_line = ""
    if exclude_words:
        sample = list(exclude_words)[:30]
        exclude_line = (
            "\nIMPORTANT: DO NOT pick any of these words "
            "(the user already has them): "
            + ", ".join(repr(w) for w in sample)
            + "."
        )

    prompt_text = _PROMPT.format(
        lang_name=lang_name,
        def_lang_name=def_lang_name,
        topic=topic,
        level_line=level_line,
        exclude_line=exclude_line,
    )

    resp = await _get_client().chat.completions.create(
        model="o4-mini",
        messages=[{"role": "user", "content": prompt_text}],
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
        if not qtype:
            continue

        if qtype == "rearrange":
            tokens = q.get("correct_tokens") or []
            tokens = [str(t).strip() for t in tokens if str(t).strip()]
            distractors = [str(x).strip() for x in (q.get("distractors") or []) if x][:3]
            if len(tokens) < 3 or len(distractors) < 2:
                continue
            quizzes.append({
                "type": "rearrange",
                "correct": " ".join(tokens),
                "correct_tokens": tokens,
                "distractors": distractors,
                "sentence_meaning": (q.get("sentence_meaning") or "").strip(),
            })
            continue

        correct = (q.get("correct") or "").strip()
        distractors = [str(x).strip() for x in (q.get("distractors") or []) if x][:3]
        if not correct or len(distractors) < 3:
            continue
        entry = {"type": qtype, "correct": correct, "distractors": distractors}
        # Legacy fill_blank kept for old cached pools — new pools won't have it
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
