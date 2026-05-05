import random
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from deps import get_current_user_id
from models import GardenPlant, Word, Harvest, WordReaction, User, PendingGift, WordNote
from schemas import (
    GardenPlantOut, GardenPlantCreate, GardenPlantMove,
    HarvestOut, ReactIn, GiftIn, ReactionOut,
    PendingGiftOut, PlantGiftIn,
    CrossbreedIn, CrossbreedOut,
    WriteNoteIn, WordNoteOut,
)
from config import get_settings as _get_app_settings
from services.openai_dictionary import crossbreed_quiz_package

router = APIRouter(prefix="/garden", tags=["garden"])

MAX_STAGE = 4   # 3 visual stages with internal stages 0-4 (waterings)

REACTION_EMOJIS = {"🌸", "💧", "✨", "🌟", "💕", "🌈"}


def _reactions_for(word: str, owner_user_id: str, db: Session) -> List[ReactionOut]:
    rows = db.query(WordReaction).filter(
        WordReaction.word == word,
        WordReaction.owner_user_id == owner_user_id,
    ).all()
    return [ReactionOut(emoji=r.emoji, from_user_id=r.from_user_id, from_name=r.from_name) for r in rows]


def _notes_for(word: str, owner_user_id: str, db: Session) -> List[WordNoteOut]:
    rows = (
        db.query(WordNote)
        .filter(WordNote.word == word, WordNote.owner_user_id == owner_user_id)
        .order_by(WordNote.created_at.desc())
        .all()
    )
    return [
        WordNoteOut(
            from_user_id=n.from_user_id,
            from_name=n.from_name,
            text=n.text,
            created_at=str(n.created_at) if n.created_at else "",
        )
        for n in rows
    ]


def _plant_to_out(plant: GardenPlant, db: Session) -> GardenPlantOut:
    word_row = db.query(Word).filter(Word.word == plant.word).first()
    reactions = _reactions_for(plant.word, plant.user_id, db)
    notes = _notes_for(plant.word, plant.user_id, db)
    gifted_by_name = None
    if plant.gifted_by:
        giftor = db.query(User).filter(User.id == plant.gifted_by).first()
        gifted_by_name = giftor.name if giftor else None
    return GardenPlantOut(
        id=plant.id,
        word=plant.word,
        x=plant.x,
        y=plant.y,
        stage=plant.stage,
        plot_id=plant.plot_id,
        scale=plant.scale,
        lang=word_row.lang if word_row else None,
        lang_color=word_row.lang_color if word_row else None,
        ipa=word_row.ipa if word_row else None,
        gloss=word_row.gloss if word_row else None,
        part_of_speech=word_row.part_of_speech if word_row else None,
        example_sentence=word_row.example_sentence if word_row else None,
        level=word_row.level if word_row else None,
        topic=word_row.topic if word_row else None,
        reactions=reactions,
        notes=notes,
        gifted_by=plant.gifted_by,
        gifted_by_name=gifted_by_name,
    )


def _harvest_out(h: Harvest, db: Session) -> HarvestOut:
    wrow = db.query(Word).filter(Word.word == h.word).first()
    reactions = _reactions_for(h.word, h.user_id, db)
    return HarvestOut(
        id=h.id, word=h.word, lang=h.lang, lang_color=h.lang_color,
        gloss=wrow.gloss if wrow else None,
        ipa=wrow.ipa if wrow else None,
        level=wrow.level if wrow else None,
        topic=wrow.topic if wrow else None,
        harvested_at=str(h.harvested_at),
        reactions=reactions,
    )


@router.get("", response_model=List[GardenPlantOut])
def get_garden(
    user_id: Optional[str] = Query(default=None),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    target = user_id or current_user_id
    plants = db.query(GardenPlant).filter(GardenPlant.user_id == target).all()
    return [_plant_to_out(p, db) for p in plants]


@router.post("", response_model=GardenPlantOut, status_code=201)
def create_plant(
    body: GardenPlantCreate,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    plant = GardenPlant(
        id=str(uuid.uuid4()),
        user_id=current_user_id,
        word=body.word,
        x=body.x,
        y=body.y,
        scale=body.scale,
        plot_id=body.plot_id,
        stage=0,
    )
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return _plant_to_out(plant, db)


@router.patch("/{plant_id}", response_model=GardenPlantOut)
def move_plant(
    plant_id: str,
    body: GardenPlantMove,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    plant = db.query(GardenPlant).filter(
        GardenPlant.id == plant_id,
        GardenPlant.user_id == current_user_id,
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    if body.x is not None: plant.x = body.x
    if body.y is not None: plant.y = body.y
    if body.scale is not None: plant.scale = body.scale
    if body.plot_id is not None: plant.plot_id = body.plot_id
    db.commit()
    db.refresh(plant)
    return _plant_to_out(plant, db)


@router.post("/{plant_id}/harvest", response_model=HarvestOut, status_code=201)
def harvest_plant(
    plant_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    plant = db.query(GardenPlant).filter(
        GardenPlant.id == plant_id,
        GardenPlant.user_id == current_user_id,
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    if plant.stage < MAX_STAGE:
        raise HTTPException(status_code=400, detail="Plant must be fully grown before harvesting")

    word_row = db.query(Word).filter(Word.word == plant.word).first()
    harvest = Harvest(
        user_id=current_user_id,
        word=plant.word,
        lang=word_row.lang if word_row else "Unknown",
        lang_color=word_row.lang_color if word_row else "#888888",
    )
    db.add(harvest)
    db.delete(plant)
    db.commit()
    db.refresh(harvest)
    return _harvest_out(harvest, db)


@router.get("/collection", response_model=List[HarvestOut])
def get_collection(
    user_id: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    lang: Optional[str] = Query(default=None),
    reaction: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    target_id = user_id or current_user_id
    if target_id != current_user_id:
        target = db.query(User).filter(User.id == target_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        if target.collection_locked:
            raise HTTPException(status_code=403, detail="This collection is private")

    query = db.query(Harvest).filter(Harvest.user_id == target_id)
    if q and q.strip():
        query = query.filter(Harvest.word.ilike(f"%{q.strip()}%"))
    if lang and lang.strip():
        query = query.filter(Harvest.lang == lang.strip())
    if reaction and reaction.strip():
        reacted_words = db.query(WordReaction.word).filter(
            WordReaction.owner_user_id == target_id,
            WordReaction.emoji == reaction.strip(),
        ).subquery()
        query = query.filter(Harvest.word.in_(reacted_words))
    rows = query.order_by(Harvest.harvested_at.desc()).offset(skip).limit(limit).all()
    return [_harvest_out(h, db) for h in rows]


@router.post("/react", status_code=201)
def react_to_plant(
    body: ReactIn,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if body.emoji not in REACTION_EMOJIS:
        raise HTTPException(status_code=400, detail="Invalid emoji")
    plant = db.query(GardenPlant).filter(
        GardenPlant.user_id == body.owner_user_id,
        GardenPlant.word == body.word,
    ).first()
    if not plant or plant.stage < MAX_STAGE:
        raise HTTPException(status_code=400, detail="Only fully grown plants can receive compliments")
    already = db.query(WordReaction).filter(
        WordReaction.word == body.word,
        WordReaction.owner_user_id == body.owner_user_id,
    ).first()
    if already:
        raise HTTPException(status_code=409, detail="This plant already has a compliment")
    me = db.query(User).filter(User.id == current_user_id).first()
    db.add(WordReaction(
        word=body.word,
        owner_user_id=body.owner_user_id,
        from_user_id=current_user_id,
        from_name=me.name if me else "",
        emoji=body.emoji,
    ))
    db.commit()
    return {"ok": True}


@router.post("/note", status_code=201, response_model=WordNoteOut)
def write_note(
    body: WriteNoteIn,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Leave a short text note on one of a friend's plants. One note per
    (sender, owner, word) — submitting again replaces the previous text."""
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Note can't be empty")
    # Notes are intentionally one short sentence.
    if len(text) > 80:
        raise HTTPException(status_code=400, detail="Note too long (max 80 chars)")
    if body.owner_user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Notes are for friends' plants")
    plant = db.query(GardenPlant).filter(
        GardenPlant.user_id == body.owner_user_id,
        GardenPlant.word == body.word,
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    me = db.query(User).filter(User.id == current_user_id).first()
    # Notes are write-once: each visitor gets a single permanent note per
    # plant. Re-submitting is rejected so the message can't be edited away.
    existing = db.query(WordNote).filter(
        WordNote.word == body.word,
        WordNote.owner_user_id == body.owner_user_id,
        WordNote.from_user_id == current_user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="You've already left a note on this plant")
    n = WordNote(
        word=body.word,
        owner_user_id=body.owner_user_id,
        from_user_id=current_user_id,
        from_name=me.name if me else "",
        text=text,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return WordNoteOut(
        from_user_id=n.from_user_id,
        from_name=n.from_name,
        text=n.text,
        created_at=str(n.created_at) if n.created_at else "",
    )


@router.post("/gift", status_code=201)
def gift_seed(
    body: GiftIn,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if body.to_user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot gift to yourself")

    has_word = db.query(Harvest).filter(
        Harvest.user_id == current_user_id,
        Harvest.word == body.word,
    ).first()
    if not has_word:
        raise HTTPException(status_code=403, detail="You don't have this word in your collection")

    already_planted = db.query(GardenPlant).filter(
        GardenPlant.user_id == body.to_user_id,
        GardenPlant.word == body.word,
    ).first()
    if already_planted:
        raise HTTPException(status_code=409, detail="Friend already has this plant")

    already_pending = db.query(PendingGift).filter(
        PendingGift.to_user_id == body.to_user_id,
        PendingGift.word == body.word,
    ).first()
    if already_pending:
        raise HTTPException(status_code=409, detail="Already gifted to this friend")

    me = db.query(User).filter(User.id == current_user_id).first()
    word_row = db.query(Word).filter(Word.word == body.word).first()
    gift = PendingGift(
        to_user_id=body.to_user_id,
        from_user_id=current_user_id,
        from_name=me.name if me else "",
        word=body.word,
        lang=word_row.lang if word_row else None,
        lang_color=word_row.lang_color if word_row else None,
    )
    db.add(gift)
    db.commit()
    db.refresh(gift)
    return {"ok": True, "gift_id": gift.id}


@router.get("/pending-gifts", response_model=List[PendingGiftOut])
def get_pending_gifts(
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    gifts = db.query(PendingGift).filter(
        PendingGift.to_user_id == current_user_id,
    ).order_by(PendingGift.created_at.asc()).all()
    return [PendingGiftOut(
        id=g.id, from_user_id=g.from_user_id, from_name=g.from_name,
        word=g.word, lang=g.lang, lang_color=g.lang_color,
    ) for g in gifts]


@router.post("/pending-gifts/{gift_id}/plant", response_model=GardenPlantOut, status_code=201)
def plant_pending_gift(
    gift_id: int,
    body: PlantGiftIn,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    gift = db.query(PendingGift).filter(
        PendingGift.id == gift_id,
        PendingGift.to_user_id == current_user_id,
    ).first()
    if not gift:
        raise HTTPException(status_code=404, detail="Gift not found")

    plant = GardenPlant(
        id=str(uuid.uuid4()),
        user_id=current_user_id,
        word=gift.word,
        x=body.x, y=body.y,
        scale=1.85, plot_id=0, stage=0,
        gifted_by=gift.from_user_id,
    )
    db.add(plant)
    db.delete(gift)
    db.commit()
    db.refresh(plant)
    return _plant_to_out(plant, db)


@router.post("/crossbreed", response_model=CrossbreedOut)
async def crossbreed(
    body: CrossbreedIn,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Combine two of the user's harvested words into a new related word."""
    if body.word1 == body.word2:
        raise HTTPException(status_code=400, detail="Pick two different words")

    h1 = db.query(Harvest).filter(Harvest.user_id == current_user_id, Harvest.word == body.word1).first()
    h2 = db.query(Harvest).filter(Harvest.user_id == current_user_id, Harvest.word == body.word2).first()
    if not h1 or not h2:
        raise HTTPException(status_code=403, detail="You must have harvested both words")

    w1 = db.query(Word).filter(Word.word == body.word1).first()
    w2 = db.query(Word).filter(Word.word == body.word2).first()

    # Daily quota — crossbreeding uses OpenAI, so it counts toward the same 20/day cap.
    from routers.words import _check_daily_seed_quota, _consume_daily_seed, _cache_word, _user_settings
    user = _check_daily_seed_quota(current_user_id, db)
    s = _user_settings(current_user_id, db)

    # Target language: same as word1's language; fallback to user's first study lang
    target_lang_name = (w1.lang if w1 else h1.lang) or "English"
    LANG_NAME_TO_KEY = {
        "English": "english", "Vietnamese": "vietnamese", "Japanese": "japanese",
        "Chinese": "chinese", "French": "french", "German": "german", "Spanish": "spanish",
    }
    target_lang = LANG_NAME_TO_KEY.get(target_lang_name, "english")

    # Pick the higher level of the two parents
    LEVEL_RANK = {"beginner": 1, "intermediate": 2, "advanced": 3}
    parent_levels = [w.level for w in (w1, w2) if w and w.level]
    target_level = max(parent_levels, key=lambda l: LEVEL_RANK.get(l, 1)) if parent_levels else s.get("vocab_level")

    settings_obj = _get_app_settings()
    if settings_obj.word_service != "openai":
        raise HTTPException(status_code=503, detail="Crossbreeding requires OpenAI mode")

    pkg = None
    for _ in range(3):
        pkg = await crossbreed_quiz_package(
            word1=body.word1,
            word1_gloss=(w1.gloss if w1 else "") or "",
            word1_lang=(w1.lang  if w1 else h1.lang) or "",
            word2=body.word2,
            word2_gloss=(w2.gloss if w2 else "") or "",
            word2_lang=(w2.lang  if w2 else h2.lang) or "",
            target_lang=target_lang,
            vocab_level=target_level,
            definition_lang=s.get("definition_lang", "english"),
        )
        if pkg:
            break
    if not pkg:
        raise HTTPException(status_code=503, detail="Couldn't crossbreed these words. Try again.")

    target = _cache_word(pkg, db, level=target_level)
    _consume_daily_seed(user, db)

    return CrossbreedOut(
        word=target.word,
        lang=target.lang,
        lang_color=target.lang_color,
        ipa=target.ipa,
        gloss=target.gloss,
        connection=pkg.get("connection") or "",
        level=target.level,
    )


@router.patch("/{plant_id}/advance", response_model=GardenPlantOut)
def advance_plant(
    plant_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    plant = db.query(GardenPlant).filter(
        GardenPlant.id == plant_id,
        GardenPlant.user_id == current_user_id,
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    if plant.stage < MAX_STAGE:
        plant.stage += 1
        db.commit()
        db.refresh(plant)
    return _plant_to_out(plant, db)
