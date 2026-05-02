from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Date, func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=False)
    initials = Column(String(5), nullable=False)
    avatar_color = Column(String(20), nullable=False)
    email = Column(String(200), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    streak = Column(Integer, default=0)
    coins = Column(Integer, default=0)
    visits_count = Column(Integer, default=0)
    last_visit_date = Column(Date, nullable=True)
    lang_prefs = Column(String(500), nullable=True)        # JSON: ["english","japanese"]
    vocab_level = Column(String(20), nullable=True)        # "beginner" | "intermediate" | "advanced"
    topic_prefs = Column(String(500), nullable=True)       # JSON: ["nature","food",...]
    definition_lang = Column(String(20), nullable=True)    # language used for word definitions, default "english"
    collection_locked = Column(Integer, default=0, nullable=False)  # 0 = public, 1 = private
    seeds_today_count = Column(Integer, default=0, nullable=False)  # daily seeds claimed via OpenAI
    seeds_today_date = Column(Date, nullable=True)         # the date `seeds_today_count` is for
    created_at = Column(DateTime, server_default=func.now())


class Word(Base):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String(200), unique=True, nullable=False)
    lang = Column(String(100), nullable=False)
    lang_color = Column(String(20), nullable=False)
    ipa = Column(String(200), nullable=True)
    gloss = Column(Text, nullable=True)
    part_of_speech = Column(String(100), nullable=True)
    example_sentence = Column(Text, nullable=True)
    quiz_pool = Column(Text, nullable=True)  # JSON array of quiz objects
    seen = Column(Integer, default=0)
    mastery = Column(Integer, default=1)
    fetched_at = Column(DateTime, server_default=func.now())


class GardenPlant(Base):
    __tablename__ = "garden_plants"

    id = Column(String(50), primary_key=True)
    user_id = Column(String(20), nullable=False, index=True)
    word = Column(String(200), nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    stage = Column(Integer, default=0)
    plot_id = Column(Integer, default=0)
    scale = Column(Float, default=1.0)
    gifted_by = Column(String(20), nullable=True)
    planted_at = Column(DateTime, server_default=func.now())


class Friend(Base):
    __tablename__ = "friends"

    user_id = Column(String(20), primary_key=True)
    friend_id = Column(String(20), primary_key=True)


class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_user_id = Column(String(20), nullable=False, index=True)
    to_user_id = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())


class WordReaction(Base):
    __tablename__ = "word_reactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String(200), nullable=False)
    owner_user_id = Column(String(20), nullable=False, index=True)
    from_user_id = Column(String(20), nullable=False)
    from_name = Column(String(100), nullable=False, default="")
    emoji = Column(String(10), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class PendingGift(Base):
    __tablename__ = "pending_gifts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    to_user_id = Column(String(20), nullable=False, index=True)
    from_user_id = Column(String(20), nullable=False)
    from_name = Column(String(100), nullable=False, default="")
    word = Column(String(200), nullable=False)
    lang = Column(String(100), nullable=True)
    lang_color = Column(String(20), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Harvest(Base):
    __tablename__ = "harvests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(20), nullable=False, index=True)
    word = Column(String(200), nullable=False)
    lang = Column(String(100), nullable=False)
    lang_color = Column(String(20), nullable=False)
    harvested_at = Column(DateTime, server_default=func.now())
