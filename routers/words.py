import json
import random
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from deps import get_current_user_id
from models import Word, User, GardenPlant, Harvest
from schemas import WordOut, RandomWordOut, QuizOut
from services.dictionary import fetch_random_word, fetch_definition, fetch_full_quiz_package

router = APIRouter(prefix="/words", tags=["words"])
settings = get_settings()

ENGLISH_LANG  = "English"
ENGLISH_COLOR = "#5a9eb8"

FALLBACK_GLOSSES = [
    "to move from one place to another with effort",
    "a feeling of strong displeasure or annoyance",
    "the quality of being pleasant or agreeable to the senses",
    "to make something happen intentionally",
    "relating to or existing in a natural state",
    "a person who performs a specified action regularly",
    "a sudden or unexpected event or development",
    "to look carefully at something for a particular purpose",
]
FALLBACK_WORDS = ["run", "blue", "small", "joy", "food", "move"]

DAILY_SEED_LIMIT = 20  # max fresh OpenAI-generated seeds per user per day


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cache_word(pkg: dict, db: Session, level: Optional[str] = None) -> Word:
    row = db.query(Word).filter(Word.word == pkg["word"]).first()
    if row:
        changed = False
        if not row.quiz_pool and pkg.get("quizzes"):
            row.quiz_pool = json.dumps(pkg["quizzes"]); changed = True
        if not row.level and level:
            row.level = level; changed = True
        if not row.topic and pkg.get("topic"):
            row.topic = pkg["topic"]; changed = True
        if changed:
            db.commit()
        return row
    row = Word(
        word=pkg["word"],
        lang=pkg.get("lang", ENGLISH_LANG),
        lang_color=pkg.get("lang_color", ENGLISH_COLOR),
        ipa=pkg.get("ipa"),
        gloss=pkg.get("gloss"),
        part_of_speech=pkg.get("part_of_speech"),
        example_sentence=pkg.get("example_sentence"),
        quiz_pool=json.dumps(pkg["quizzes"]) if pkg.get("quizzes") else None,
        level=level,
        topic=pkg.get("topic"),
        seen=0,
        mastery=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _pick_lang(user_id: str, db: Session) -> str:
    """Pick a random language from the user's prefs, defaulting to english."""
    import json as _json
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.lang_prefs:
        return "english"
    try:
        prefs = _json.loads(user.lang_prefs)
    except Exception:
        return "english"
    return random.choice(prefs) if prefs else "english"


def _user_settings(user_id: str, db: Session) -> dict:
    """Load the user's quiz-related settings (level, topics, definition lang)."""
    import json as _json
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"vocab_level": None, "topic_prefs": None, "definition_lang": "english"}
    try:
        topics = _json.loads(user.topic_prefs) if user.topic_prefs else None
    except Exception:
        topics = None
    return {
        "vocab_level": user.vocab_level,
        "topic_prefs": topics or None,
        "definition_lang": user.definition_lang or "english",
    }


def _user_existing_words(user_id: str, db: Session) -> set:
    """Words the user already has — planted or harvested. Used to avoid repeats."""
    plants = db.query(GardenPlant.word).filter(GardenPlant.user_id == user_id).all()
    harvests = db.query(Harvest.word).filter(Harvest.user_id == user_id).all()
    return {p[0] for p in plants} | {h[0] for h in harvests}


def _check_daily_seed_quota(user_id: str, db: Session) -> User:
    """Raise 429 if the user has already claimed today's quota.
    Returns the User row so the caller can mutate the counter once they actually
    consume a seed."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    today = date.today()
    if user.seeds_today_date != today:
        # roll over to a new day
        user.seeds_today_date = today
        user.seeds_today_count = 0
    if (user.seeds_today_count or 0) >= DAILY_SEED_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Daily seed limit reached ({DAILY_SEED_LIMIT}). Try planting gifts from friends — those don't count!",
        )
    return user


def _consume_daily_seed(user: User, db: Session) -> None:
    user.seeds_today_count = (user.seeds_today_count or 0) + 1
    db.commit()


async def _fetch_or_cache_external(word_str: str, db: Session) -> Optional[Word]:
    cached = db.query(Word).filter(Word.word == word_str).first()
    if cached:
        return cached if cached.gloss else None
    definition = await fetch_definition(word_str)
    if not definition.get("gloss"):
        return None
    return _cache_word({**definition, "word": word_str, "quizzes": []}, db)


def _pad_distractors(lst: list, fallback: list, n: int = 3) -> list:
    out = list(lst)
    fb = iter(x for x in fallback if x not in out)
    while len(out) < n:
        out.append(next(fb, "a general concept"))
    return out[:n]


def _quiz_out(target: Word, quiz_type: str, correct: str, distractors: list,
              question: Optional[str] = None,
              correct_tokens: Optional[list] = None) -> QuizOut:
    return QuizOut(
        quiz_type=quiz_type,
        word=target.word,
        lang=target.lang,
        lang_color=target.lang_color,
        ipa=target.ipa,
        gloss=target.gloss or "an English word",
        question=question,
        correct=correct,
        correct_tokens=correct_tokens,
        distractors=distractors,
    )


def _pick_from_pool(target: Word, stage: int = 0) -> Optional[QuizOut]:
    """Pick quiz at pool[stage % len(pool)] so each watering gets a different type.
    Skips legacy fill_blank entries (those are no longer accepted)."""
    if not target.quiz_pool:
        return None
    try:
        pool = json.loads(target.quiz_pool)
    except Exception:
        return None
    if not pool:
        return None

    # Try `len(pool)` candidates starting at stage; skip unsupported types.
    for i in range(len(pool)):
        q = pool[(stage + i) % len(pool)]
        qtype = q.get("type")
        correct = q.get("correct", "")
        distractors = q.get("distractors", [])
        if not qtype or not correct:
            continue

        if qtype == "rearrange":
            tokens = q.get("correct_tokens") or []
            if not isinstance(tokens, list) or len(tokens) < 3 or len(distractors) < 2:
                continue
            return _quiz_out(target, "rearrange", correct, list(distractors)[:3],
                             question=q.get("sentence_meaning") or None,
                             correct_tokens=list(tokens))

        if qtype in ("meaning", "synonym", "antonym"):
            if len(distractors) < 3:
                continue
            return _quiz_out(target, qtype, correct, list(distractors)[:3])

        # Legacy fill_blank — skip; pool will get refreshed eventually
        # or another type in the pool will be used.

    return None


# ── External-mode quiz builders (DB-sourced distractors) ─────────────────────

def _meaning_quiz_external(target: Word, db: Session) -> QuizOut:
    rows = (
        db.query(Word.gloss)
        .filter(Word.gloss != None, Word.word != target.word, Word.lang == target.lang)
        .order_by(func.rand()).limit(3).all()
    )
    distractors = _pad_distractors([r[0] for r in rows if r[0]], FALLBACK_GLOSSES)
    return _quiz_out(target, "meaning", target.gloss or "an English word", distractors)




# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/quiz", response_model=QuizOut)
async def get_quiz_word(
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if settings.word_service == "openai":
        user = _check_daily_seed_quota(current_user_id, db)
        lang = _pick_lang(current_user_id, db)
        s = _user_settings(current_user_id, db)
        existing = _user_existing_words(current_user_id, db)
        for _ in range(5):
            pkg = await fetch_full_quiz_package(lang=lang, **s, exclude_words=list(existing)[:30])
            if not pkg:
                continue
            if pkg["word"] in existing:
                continue  # OpenAI returned a duplicate anyway — try again
            target = _cache_word(pkg, db, level=s.get("vocab_level"))
            quiz = _pick_from_pool(target)
            if quiz:
                _consume_daily_seed(user, db)
                return quiz
        raise HTTPException(status_code=503, detail="Could not generate a quiz. Try again.")

    for _ in range(10):
        word_str = await fetch_random_word()
        target = await _fetch_or_cache_external(word_str, db)
        if target:
            return _meaning_quiz_external(target, db)
    raise HTTPException(status_code=503, detail="Could not find a defined word. Try again.")


@router.get("/quiz/{word}", response_model=QuizOut)
def get_word_quiz(
    word: str,
    stage: int = 0,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Quiz for a specific word (watering). Cycled by stage so no type repeats."""
    target = db.query(Word).filter(Word.word == word).first()
    if not target:
        raise HTTPException(status_code=404, detail="Word not found")
    if not target.gloss:
        raise HTTPException(status_code=422, detail="No definition available for this word")

    quiz = _pick_from_pool(target, stage)
    if quiz:
        return quiz

    # Fallback for words without a pool (external mode or pre-pool words)
    return _meaning_quiz_external(target, db)


@router.get("/random", response_model=RandomWordOut)
async def get_random_word(
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if settings.word_service == "openai":
        user = _check_daily_seed_quota(current_user_id, db)
        lang = _pick_lang(current_user_id, db)
        s = _user_settings(current_user_id, db)
        existing = _user_existing_words(current_user_id, db)
        for _ in range(5):
            pkg = await fetch_full_quiz_package(lang=lang, **s, exclude_words=list(existing)[:30])
            if not pkg:
                continue
            if pkg["word"] in existing:
                continue
            target = _cache_word(pkg, db, level=s.get("vocab_level"))
            _consume_daily_seed(user, db)
            return RandomWordOut(
                word=target.word, lang=target.lang, lang_color=target.lang_color,
                ipa=target.ipa, gloss=target.gloss,
            )
        raise HTTPException(status_code=503, detail="Could not generate a word. Try again.")

    for _ in range(10):
        word_str = await fetch_random_word()
        target = await _fetch_or_cache_external(word_str, db)
        if target:
            return RandomWordOut(
                word=target.word, lang=target.lang, lang_color=target.lang_color,
                ipa=target.ipa, gloss=target.gloss,
            )
    raise HTTPException(status_code=503, detail="Could not find a defined word. Try again.")


@router.get("/{word}", response_model=WordOut)
def get_word(word: str, db: Session = Depends(get_db)):
    row = db.query(Word).filter(Word.word == word).first()
    if not row:
        raise HTTPException(status_code=404, detail="Word not found")
    return WordOut.model_validate(row)
