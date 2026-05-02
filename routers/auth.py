import json
from datetime import datetime, timedelta, timezone, date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from jose import jwt
from sqlalchemy.orm import Session

from database import get_db
from models import User, GardenPlant
from schemas import RegisterIn, LoginIn, AuthOut, UserOut
from config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _make_token(user_id: str) -> str:
    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(days=settings.token_expire_days)
    return jwt.encode({"sub": user_id, "exp": exp}, settings.secret_key, algorithm="HS256")


def update_streak(user: User, db: Session) -> None:
    """Update streak and visit count based on today's date. Safe to call on every app open."""
    today = date.today()
    last = user.last_visit_date

    if last == today:
        return  # already counted today

    user.visits_count = (user.visits_count or 0) + 1

    if last is not None and (today - last).days == 1:
        user.streak = (user.streak or 0) + 1
    elif last != today:
        user.streak = 1  # missed a day or first ever visit

    user.last_visit_date = today
    db.commit()


def _user_out(user: User, db: Session) -> UserOut:
    plants_count = db.query(GardenPlant).filter(GardenPlant.user_id == user.id).count()
    try:
        lang_prefs = json.loads(user.lang_prefs) if user.lang_prefs else []
    except Exception:
        lang_prefs = []
    return UserOut(
        id=user.id,
        name=user.name,
        initials=user.initials,
        avatar_color=user.avatar_color,
        streak=user.streak,
        coins=user.coins,
        visits_count=user.visits_count,
        plants_count=plants_count,
        lang_prefs=lang_prefs,
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
