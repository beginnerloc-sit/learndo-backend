import json
from fastapi import APIRouter, Depends, HTTPException
from routers.auth import update_streak
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from deps import get_current_user_id
from models import User, GardenPlant, Friend, Harvest
from schemas import UserOut, LeaderboardEntry, LangPrefsIn, LockCollectionIn

router = APIRouter(prefix="/users", tags=["users"])

VALID_LANGS = {"english", "vietnamese", "japanese", "chinese", "french", "german", "spanish"}


def _parse_lang_prefs(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def _user_to_out(user: User, db: Session) -> UserOut:
    plants_count = (
        db.query(GardenPlant)
        .filter(GardenPlant.user_id == user.id)
        .count()
    )
    return UserOut(
        id=user.id,
        name=user.name,
        initials=user.initials,
        avatar_color=user.avatar_color,
        streak=user.streak,
        coins=user.coins,
        visits_count=user.visits_count,
        plants_count=plants_count,
        lang_prefs=_parse_lang_prefs(user.lang_prefs),
        collection_locked=bool(user.collection_locked),
    )


@router.get("/me", response_model=UserOut)
def get_me(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_streak(user, db)
    return _user_to_out(user, db)


@router.patch("/me/lang-prefs", response_model=UserOut)
def update_lang_prefs(
    body: LangPrefsIn,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    langs = [l for l in body.langs if l in VALID_LANGS][:3]
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.lang_prefs = json.dumps(langs)
    db.commit()
    db.refresh(user)
    return _user_to_out(user, db)


@router.patch("/me/collection-lock", response_model=UserOut)
def update_collection_lock(
    body: LockCollectionIn,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.collection_locked = 1 if body.locked else 0
    db.commit()
    db.refresh(user)
    return _user_to_out(user, db)


@router.get("/me/friends", response_model=List[UserOut])
def get_my_friends(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    friend_ids = (
        db.query(Friend.friend_id)
        .filter(Friend.user_id == user_id)
        .all()
    )
    ids = [row[0] for row in friend_ids]
    users = db.query(User).filter(User.id.in_(ids)).all()
    return [_user_to_out(u, db) for u in users]


@router.get("/leaderboard/top", response_model=List[LeaderboardEntry])
def get_leaderboard(
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(User, func.count(Harvest.id).label("harvest_count"))
        .outerjoin(Harvest, Harvest.user_id == User.id)
        .group_by(User.id)
        .order_by(func.count(Harvest.id).desc())
        .limit(20)
        .all()
    )
    return [
        LeaderboardEntry(
            id=u.id,
            name=u.name,
            initials=u.initials,
            avatar_color=u.avatar_color,
            streak=u.streak,
            harvest_count=count,
        )
        for u, count in rows
    ]


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_out(user, db)
