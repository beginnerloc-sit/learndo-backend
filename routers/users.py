import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from routers.auth import update_streak
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from deps import get_current_user_id
from models import User, GardenPlant, Friend, FriendRequest, Harvest
from schemas import (
    UserOut, LeaderboardEntry, LangPrefsIn, UserSettingsIn,
    LockCollectionIn, AddFriendIn, FriendRequestOut,
)

router = APIRouter(prefix="/users", tags=["users"])

VALID_LANGS = {"english", "vietnamese", "japanese", "chinese", "french", "german", "spanish"}
VALID_LEVELS = {"beginner", "intermediate", "advanced"}
VALID_TOPICS = {
    "nature", "food", "emotion", "science", "music", "architecture",
    "geography", "sport", "technology", "philosophy", "medicine", "art",
    "mythology", "law", "economics", "literature", "astronomy", "cooking",
}


def _parse_json_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def _user_to_out(user: User, db: Session, streak_check=None) -> UserOut:
    plants_count = (
        db.query(GardenPlant)
        .filter(GardenPlant.user_id == user.id)
        .count()
    )
    harvest_count = (
        db.query(Harvest)
        .filter(Harvest.user_id == user.id)
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
        harvest_count=harvest_count,
        lang_prefs=_parse_json_list(user.lang_prefs),
        vocab_level=user.vocab_level,
        topic_prefs=_parse_json_list(user.topic_prefs),
        definition_lang=user.definition_lang or "english",
        collection_locked=bool(user.collection_locked),
        tutorial_completed=bool(user.tutorial_completed),
        streak_check=streak_check,
    )


@router.get("/me", response_model=UserOut)
def get_me(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    info = update_streak(user, db)
    return _user_to_out(user, db, streak_check=info)


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


@router.patch("/me/settings", response_model=UserOut)
def update_settings(
    body: UserSettingsIn,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.langs is not None:
        langs = [l for l in body.langs if l in VALID_LANGS][:3]
        user.lang_prefs = json.dumps(langs)
    if body.vocab_level is not None:
        if body.vocab_level not in VALID_LEVELS:
            raise HTTPException(status_code=400, detail="Invalid vocab_level")
        user.vocab_level = body.vocab_level
    if body.topic_prefs is not None:
        topics = [t for t in body.topic_prefs if t in VALID_TOPICS][:6]
        user.topic_prefs = json.dumps(topics)
    if body.definition_lang is not None:
        if body.definition_lang not in VALID_LANGS:
            raise HTTPException(status_code=400, detail="Invalid definition_lang")
        user.definition_lang = body.definition_lang
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


@router.post("/me/tutorial-complete", response_model=UserOut)
def complete_tutorial(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Marks the gameplay walkthrough as completed for this user.
    Idempotent — safe to call repeatedly."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.tutorial_completed = 1
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


def _make_friends(user_id: str, friend_id: str, db: Session) -> None:
    """Insert both directions of the friendship, idempotently."""
    if not db.query(Friend).filter_by(user_id=user_id, friend_id=friend_id).first():
        db.add(Friend(user_id=user_id, friend_id=friend_id))
    if not db.query(Friend).filter_by(user_id=friend_id, friend_id=user_id).first():
        db.add(Friend(user_id=friend_id, friend_id=user_id))


def _request_out(req: FriendRequest, other: User, db: Session) -> FriendRequestOut:
    return FriendRequestOut(id=req.id, user=_user_to_out(other, db), created_at=str(req.created_at))


@router.post("/me/friend-requests", response_model=FriendRequestOut, status_code=status.HTTP_201_CREATED)
def send_friend_request(
    body: AddFriendIn,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if body.friend_id == user_id:
        raise HTTPException(status_code=400, detail="Can't befriend yourself")
    target = db.query(User).filter(User.id == body.friend_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if db.query(Friend).filter_by(user_id=user_id, friend_id=body.friend_id).first():
        raise HTTPException(status_code=409, detail="Already friends")

    # If the other user has already sent ME a request, auto-accept (mutual interest).
    incoming = db.query(FriendRequest).filter_by(
        from_user_id=body.friend_id, to_user_id=user_id,
    ).first()
    if incoming:
        _make_friends(user_id, body.friend_id, db)
        out = _request_out(incoming, target, db)
        db.delete(incoming)
        db.commit()
        return out

    # Already sent → return existing (idempotent)
    existing = db.query(FriendRequest).filter_by(
        from_user_id=user_id, to_user_id=body.friend_id,
    ).first()
    if existing:
        return _request_out(existing, target, db)

    fr = FriendRequest(from_user_id=user_id, to_user_id=body.friend_id)
    db.add(fr)
    db.commit()
    db.refresh(fr)
    return _request_out(fr, target, db)


@router.get("/me/friend-requests", response_model=List[FriendRequestOut])
def get_incoming_requests(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rows = db.query(FriendRequest).filter_by(to_user_id=user_id).order_by(FriendRequest.created_at.desc()).all()
    out = []
    for r in rows:
        u = db.query(User).filter(User.id == r.from_user_id).first()
        if u:
            out.append(_request_out(r, u, db))
    return out


@router.get("/me/friend-requests/sent", response_model=List[FriendRequestOut])
def get_outgoing_requests(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rows = db.query(FriendRequest).filter_by(from_user_id=user_id).order_by(FriendRequest.created_at.desc()).all()
    out = []
    for r in rows:
        u = db.query(User).filter(User.id == r.to_user_id).first()
        if u:
            out.append(_request_out(r, u, db))
    return out


@router.post("/me/friend-requests/{request_id}/accept", response_model=UserOut)
def accept_friend_request(
    request_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    fr = db.query(FriendRequest).filter_by(id=request_id, to_user_id=user_id).first()
    if not fr:
        raise HTTPException(status_code=404, detail="Request not found")
    other = db.query(User).filter(User.id == fr.from_user_id).first()
    if not other:
        db.delete(fr); db.commit()
        raise HTTPException(status_code=404, detail="Sender no longer exists")
    _make_friends(user_id, fr.from_user_id, db)
    db.delete(fr)
    db.commit()
    return _user_to_out(other, db)


@router.delete("/me/friend-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def decline_or_cancel_request(
    request_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    fr = db.query(FriendRequest).filter(
        FriendRequest.id == request_id,
        or_(FriendRequest.from_user_id == user_id, FriendRequest.to_user_id == user_id),
    ).first()
    if not fr:
        raise HTTPException(status_code=404, detail="Request not found")
    db.delete(fr)
    db.commit()
    return None


@router.delete("/me/friends/{friend_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_friend(
    friend_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    db.query(Friend).filter(
        or_(
            (Friend.user_id == user_id) & (Friend.friend_id == friend_id),
            (Friend.user_id == friend_id) & (Friend.friend_id == user_id),
        )
    ).delete(synchronize_session=False)
    db.commit()
    return None


@router.get("/search", response_model=List[UserOut])
def search_users(
    q: str = Query(..., min_length=1, max_length=100),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Search users by name or email (case-insensitive partial match). Excludes self."""
    pattern = f"%{q.strip()}%"
    users = (
        db.query(User)
        .filter(User.id != user_id)
        .filter(or_(User.name.ilike(pattern), User.email.ilike(pattern)))
        .order_by(User.name.asc())
        .limit(20)
        .all()
    )
    return [_user_to_out(u, db) for u in users]


@router.get("/suggestions", response_model=List[UserOut])
def get_friend_suggestions(
    limit: int = Query(default=5, ge=1, le=20),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Random sample of users who are NOT yet friends — for the discover/
    suggestions strip in FriendsScreen. Excludes:
      - self
      - existing friends
      - users with a pending request in either direction
    """
    # IDs to exclude — self + current friends + pending request counterparts
    exclude_ids = {user_id}
    exclude_ids.update(f.friend_id for f in db.query(Friend.friend_id).filter(Friend.user_id == user_id).all())
    exclude_ids.update(r.to_user_id for r in db.query(FriendRequest.to_user_id).filter(FriendRequest.from_user_id == user_id).all())
    exclude_ids.update(r.from_user_id for r in db.query(FriendRequest.from_user_id).filter(FriendRequest.to_user_id == user_id).all())

    users = (
        db.query(User)
        .filter(~User.id.in_(exclude_ids))
        .order_by(func.rand())
        .limit(limit)
        .all()
    )
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
