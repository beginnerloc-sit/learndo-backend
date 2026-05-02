from pydantic import BaseModel, ConfigDict
from typing import List, Optional


# ---------- User ----------

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    initials: str
    avatar_color: str
    streak: int
    coins: int
    visits_count: int
    plants_count: int = 0
    lang_prefs: Optional[List[str]] = []
    vocab_level: Optional[str] = None
    topic_prefs: Optional[List[str]] = []
    definition_lang: Optional[str] = "english"
    collection_locked: bool = False


class LangPrefsIn(BaseModel):
    langs: List[str]


class AddFriendIn(BaseModel):
    friend_id: str


class FriendRequestOut(BaseModel):
    id: int
    user: UserOut       # the other party — sender for incoming, recipient for outgoing
    created_at: str


class UserSettingsIn(BaseModel):
    """All-in-one settings update — every field optional, only set ones change."""
    langs: Optional[List[str]] = None
    vocab_level: Optional[str] = None
    topic_prefs: Optional[List[str]] = None
    definition_lang: Optional[str] = None


class LockCollectionIn(BaseModel):
    locked: bool


# ---------- Word ----------

class WordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    word: str
    lang: str
    lang_color: str
    ipa: Optional[str] = None
    gloss: Optional[str] = None
    part_of_speech: Optional[str] = None
    seen: int = 0
    mastery: int = 1


class RandomWordOut(BaseModel):
    word: str
    lang: str
    lang_color: str
    ipa: Optional[str] = None
    gloss: Optional[str] = None


# ---------- Garden ----------

class ReactionOut(BaseModel):
    emoji: str
    from_user_id: str
    from_name: str


class GardenPlantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    word: str
    x: float
    y: float
    stage: int
    plot_id: int
    scale: float
    lang: Optional[str] = None
    lang_color: Optional[str] = None
    ipa: Optional[str] = None
    gloss: Optional[str] = None
    part_of_speech: Optional[str] = None
    example_sentence: Optional[str] = None
    reactions: List[ReactionOut] = []
    gifted_by: Optional[str] = None
    gifted_by_name: Optional[str] = None


class GiftIn(BaseModel):
    to_user_id: str
    word: str

class PendingGiftOut(BaseModel):
    id: int
    from_user_id: str
    from_name: str
    word: str
    lang: Optional[str] = None
    lang_color: Optional[str] = None

class PlantGiftIn(BaseModel):
    x: float
    y: float


class ReactIn(BaseModel):
    owner_user_id: str
    word: str
    emoji: str


class GardenPlantCreate(BaseModel):
    word: str
    x: float
    y: float
    scale: float = 1.0
    plot_id: int = 0
    user_id: Optional[str] = None  # if omitted, defaults to current user


class GardenPlantMove(BaseModel):
    """Partial update — only position fields; all optional."""
    x: Optional[float] = None
    y: Optional[float] = None
    scale: Optional[float] = None
    plot_id: Optional[int] = None


# ---------- Auth ----------

class RegisterIn(BaseModel):
    name: str
    email: str
    password: str

class LoginIn(BaseModel):
    email: str
    password: str

class AuthOut(BaseModel):
    token: str
    user: UserOut


# ---------- Harvest ----------

class HarvestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    word: str
    lang: str
    lang_color: str
    gloss: Optional[str] = None
    ipa: Optional[str] = None
    harvested_at: str = ""
    reactions: List[ReactionOut] = []


class LeaderboardEntry(BaseModel):
    id: str
    name: str
    initials: str
    avatar_color: str
    streak: int
    harvest_count: int


# ---------- Quiz ----------

class QuizOut(BaseModel):
    quiz_type: str          # "meaning" | "rearrange" | "synonym" | "antonym"
    word: str
    lang: str
    lang_color: str
    ipa: Optional[str] = None
    gloss: str              # always the definition, shown as context
    question: Optional[str] = None        # rearrange: sentence meaning shown as hint; legacy fill_blank: sentence with ___
    correct: str            # for rearrange: tokens joined by space; for others: the answer label
    correct_tokens: Optional[List[str]] = None  # rearrange-only: ordered correct tokens
    distractors: List[str]  # for rearrange: extra distractor tokens; for others: 3 wrong answer labels
