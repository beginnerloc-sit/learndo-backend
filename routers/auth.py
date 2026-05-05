import json
from datetime import datetime, timedelta, timezone, date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from jose import jwt
from sqlalchemy.orm import Session

from database import get_db
from models import User, GardenPlant, Harvest
from schemas import RegisterIn, LoginIn, AuthOut, UserOut
from config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _make_token(user_id: str) -> str:
    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(days=settings.token_expire_days)
    return jwt.encode({"sub": user_id, "exp": exp}, settings.secret_key, algorithm="HS256")


def update_streak(user: User, db: Session) -> dict:
    """Update streak and visit count based on today's date.

    Safe to call on every app open. Returns metadata so the UI can show a
    one-time "daily check-in" prompt the first time a user opens the app on
    a given day:
        first_today      — True iff this call transitioned last_visit_date to today
        was_consecutive  — True iff streak went up (didn't miss a day)
        streak           — the user's streak after this call
    """
    today = date.today()
    last = user.last_visit_date

    if last == today:
        return {"first_today": False, "was_consecutive": False, "streak": user.streak or 0}

    user.visits_count = (user.visits_count or 0) + 1

    was_consecutive = False
    if last is not None and (today - last).days == 1:
        user.streak = (user.streak or 0) + 1
        was_consecutive = True
    elif last != today:
        user.streak = 1  # missed a day or first ever visit

    user.last_visit_date = today
    db.commit()
    return {"first_today": True, "was_consecutive": was_consecutive, "streak": user.streak or 0}


def _safe_json_list(raw):
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def _user_out(user: User, db: Session) -> UserOut:
    plants_count = db.query(GardenPlant).filter(GardenPlant.user_id == user.id).count()
    harvest_count = db.query(Harvest).filter(Harvest.user_id == user.id).count()
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
        lang_prefs=_safe_json_list(user.lang_prefs),
        vocab_level=user.vocab_level,
        topic_prefs=_safe_json_list(user.topic_prefs),
        definition_lang=user.definition_lang or "english",
        collection_locked=bool(user.collection_locked),
        tutorial_completed=bool(user.tutorial_completed),
    )


@router.post("/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=f"u{uuid4().hex[:8]}",
        name=body.name.strip(),
        initials=body.name.strip()[0].upper(),
        avatar_color="#3e6534",
        email=body.email.lower().strip(),
        password_hash=pwd_ctx.hash(body.password),
        streak=0,
        coins=100,
        visits_count=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    update_streak(user, db)
    return AuthOut(token=_make_token(user.id), user=_user_out(user, db))


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not user or not user.password_hash or not pwd_ctx.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    update_streak(user, db)
    return AuthOut(token=_make_token(user.id), user=_user_out(user, db))
