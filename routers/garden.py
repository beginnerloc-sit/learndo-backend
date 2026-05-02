import random
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from deps import get_current_user_id
from models import GardenPlant, Word, Harvest, WordReaction, User, PendingGift
from schemas import (
    GardenPlantOut, GardenPlantCreate, GardenPlantMove,
    HarvestOut, ReactIn, GiftIn, ReactionOut,
    PendingGiftOut, PlantGiftIn,
)

router = APIRouter(prefix="/garden", tags=["garden"])

MAX_STAGE = 5

REACTION_EMOJIS = {"🌸", "💧", "✨", "🌟", "💕", "🌈"}


def _reactions_for(word: str, owner_user_id: str, db: Session) -> List[ReactionOut]:
    rows = db.query(WordReaction).filter(
        WordReaction.word == word,
        WordReaction.owner_user_id == owner_user_id,
    ).all()
    return [ReactionOut(emoji=r.emoji, from_user_id=r.from_user_id, from_name=r.from_name) for r in rows]


def _plant_to_out(plant: GardenPlant, db: Session) -> GardenPlantOut:
    word_row = db.query(Word).filter(Word.word == plant.word).first()
    reactions = _reactions_for(plant.word, plant.user_id, db)
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
        reactions=reactions,
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
        raise HTTPException(status_code=400, detail="Plant must reach stage 5 before harvesting")

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
