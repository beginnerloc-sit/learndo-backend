import json
import random
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from deps import get_current_user_id
from models import Word, User
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cache_word(pkg: dict, db: Session) -> Word:
    row = db.query(Word).filter(Word.word == pkg["word"]).first()
    if row:
        if not row.quiz_pool and pkg.get("quizzes"):
            row.quiz_pool = json.dumps(pkg["quizzes"])
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
              question: Optional[str] = None) -> QuizOut:
    return QuizOut(
        quiz_type=quiz_type,
        word=target.word,
        lang=target.lang,
        lang_color=target.lang_color,
        ipa=target.ipa,
        gloss=target.gloss or "an English word",
        question=question,
        correct=correct,
        distractors=distractors,
    )


def _pick_from_pool(target: Word, stage: int = 0) -> Optional[QuizOut]:
    """Pick quiz at pool[stage % len(pool)] so each watering gets a different type."""
    if not target.quiz_pool:
        return None
    try:
        pool = json.loads(target.quiz_pool)
    except Exception:
        return None
    if not pool:
        return None

    q = pool[stage % len(pool)]
    qtype = q.get("type")
    correct = q.get("correct", "")
    distractors = q.get("distractors", [])
    question = q.get("question")

    if not qtype or not correct or len(distractors) < 3:
        return None
    if qtype == "fill_blank" and (not question or "___" not in question):
        return None

    return _quiz_out(target, qtype, correct, distractors[:3], question)


# ── External-mode quiz builders (DB-sourced distractors) ─────────────────────

def _meaning_quiz_external(target: Word, db: Session) -> QuizOut:
    rows = (
        db.query(Word.gloss)
        .filter(Word.gloss != None, Word.word != target.word, Word.lang == target.lang)
        .order_by(func.rand()).limit(3).all()
    )
    distractors = _pad_distractors([r[0] for r in rows if r[0]], FALLBACK_GLOSSES)
    return _quiz_out(target, "meaning", target.gloss or "an English word", distractors)


def _fill_blank_quiz_external(target: Word, db: Session) -> QuizOut:
    rows = (
        db.query(Word.word)
        .filter(Word.word != target.word, Word.lang == target.lang)
        .order_by(func.rand()).limit(3).all()
    )
    distractors = _pad_distractors([r[0] for r in rows if r[0]], FALLBACK_WORDS)
    return _quiz_out(target, "fill_blank", target.word, distractors, target.example_sentence)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/quiz", response_model=QuizOut)
async def get_quiz_word(
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if settings.word_service == "openai":
        lang = _pick_lang(current_user_id, db)
        for _ in range(5):
            pkg = await fetch_full_quiz_package(lang=lang)
            if not pkg:
                continue
            target = _cache_word(pkg, db)
            quiz = _pick_from_pool(target)
            if quiz:
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
    if target.example_sentence and "___" in target.example_sentence and random.random() > 0.4:
        return _fill_blank_quiz_external(target, db)
    return _meaning_quiz_external(target, db)


@router.get("/random", response_model=RandomWordOut)
async def get_random_word(
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if settings.word_service == "openai":
        lang = _pick_lang(current_user_id, db)
        for _ in range(5):
            pkg = await fetch_full_quiz_package(lang=lang)
            if pkg:
                target = _cache_word(pkg, db)
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
