"""
Seed the database with initial users, words, friends, and garden plants.
Idempotent: skips insertion if users table is already populated.
"""

from passlib.context import CryptContext
from sqlalchemy.orm import Session
from models import User, Word, Friend, GardenPlant

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

USERS = [
    {"id": "u1", "name": "Loctien", "initials": "L", "avatar_color": "#3e6534",
     "email": "loctien@demo.com", "_demo_password": "demo1234",
     "streak": 12, "coins": 1240, "visits_count": 8},
    {"id": "u2", "name": "Amara",   "initials": "A", "avatar_color": "#b53a6a", "streak": 18, "coins": 2180, "visits_count": 3},
    {"id": "u3", "name": "Felix",   "initials": "F", "avatar_color": "#5a3e8e", "streak": 9,  "coins": 890,  "visits_count": 2},
    {"id": "u4", "name": "Mia",     "initials": "M", "avatar_color": "#3e8a5a", "streak": 24, "coins": 3100, "visits_count": 5},
    {"id": "u5", "name": "Soren",   "initials": "S", "avatar_color": "#c89a2e", "streak": 6,  "coins": 540,  "visits_count": 1},
    {"id": "u6", "name": "Yuki",    "initials": "Y", "avatar_color": "#e87aa3", "streak": 31, "coins": 4450, "visits_count": 9},
    {"id": "u7", "name": "Carlos",  "initials": "C", "avatar_color": "#5a9eb8", "streak": 15, "coins": 1680, "visits_count": 4},
]

WORD_INFO = {
    "manzana":  {"lang": "Spanish",  "lang_color": "#c1325a", "ipa": "manˈsa.na",   "gloss": "apple",          "seen": 14, "mastery": 4},
    "casa":     {"lang": "Spanish",  "lang_color": "#c1325a", "ipa": "ˈka.sa",      "gloss": "house",          "seen": 22, "mastery": 5},
    "agua":     {"lang": "Spanish",  "lang_color": "#c1325a", "ipa": "ˈa.ɣwa",      "gloss": "water",          "seen": 18, "mastery": 4},
    "hola":     {"lang": "Spanish",  "lang_color": "#c1325a", "ipa": "ˈo.la",       "gloss": "hello",          "seen": 27, "mastery": 5},
    "verde":    {"lang": "Spanish",  "lang_color": "#c1325a", "ipa": "ˈbeɾ.ðe",     "gloss": "green",          "seen": 9,  "mastery": 3},
    "perro":    {"lang": "Spanish",  "lang_color": "#c1325a", "ipa": "ˈpe.ro",      "gloss": "dog",            "seen": 11, "mastery": 3},
    "flor":     {"lang": "Spanish",  "lang_color": "#c1325a", "ipa": "floɾ",        "gloss": "flower",         "seen": 6,  "mastery": 2},
    "estrella": {"lang": "Spanish",  "lang_color": "#c1325a", "ipa": "esˈtɾe.ʎa",   "gloss": "star",           "seen": 4,  "mastery": 2},
    "本":        {"lang": "Japanese", "lang_color": "#b53a6a", "ipa": "hon",         "gloss": "book",           "seen": 21, "mastery": 5},
    "りんご":    {"lang": "Japanese", "lang_color": "#b53a6a", "ipa": "ringo",       "gloss": "apple",          "seen": 12, "mastery": 4},
    "猫":        {"lang": "Japanese", "lang_color": "#b53a6a", "ipa": "neko",        "gloss": "cat",            "seen": 25, "mastery": 5},
    "さくら":    {"lang": "Japanese", "lang_color": "#b53a6a", "ipa": "sakura",      "gloss": "cherry blossom", "seen": 9,  "mastery": 3},
    "木":        {"lang": "Japanese", "lang_color": "#b53a6a", "ipa": "ki",          "gloss": "tree",           "seen": 14, "mastery": 4},
    "言葉":      {"lang": "Japanese", "lang_color": "#b53a6a", "ipa": "kotoba",      "gloss": "word",           "seen": 8,  "mastery": 3},
    "幸せ":      {"lang": "Japanese", "lang_color": "#b53a6a", "ipa": "shiawase",    "gloss": "happiness",      "seen": 6,  "mastery": 2},
    "すし":      {"lang": "Japanese", "lang_color": "#b53a6a", "ipa": "sushi",       "gloss": "sushi",          "seen": 16, "mastery": 4},
    "ゆめ":      {"lang": "Japanese", "lang_color": "#b53a6a", "ipa": "yume",        "gloss": "dream",          "seen": 5,  "mastery": 2},
    "Buch":     {"lang": "German",   "lang_color": "#5a3e8e", "ipa": "buːx",        "gloss": "book",           "seen": 13, "mastery": 4},
    "Haus":     {"lang": "German",   "lang_color": "#5a3e8e", "ipa": "haʊs",        "gloss": "house",          "seen": 17, "mastery": 4},
    "rot":      {"lang": "German",   "lang_color": "#5a3e8e", "ipa": "ʁoːt",        "gloss": "red",            "seen": 10, "mastery": 3},
    "Hund":     {"lang": "German",   "lang_color": "#5a3e8e", "ipa": "hʊnt",        "gloss": "dog",            "seen": 8,  "mastery": 3},
    "danke":    {"lang": "German",   "lang_color": "#5a3e8e", "ipa": "ˈdaŋ.kə",     "gloss": "thank you",      "seen": 19, "mastery": 5},
    "soleil":   {"lang": "French",   "lang_color": "#d4812a", "ipa": "sɔ.lɛj",      "gloss": "sun",            "seen": 18, "mastery": 5},
    "pomme":    {"lang": "French",   "lang_color": "#d4812a", "ipa": "pɔm",         "gloss": "apple",          "seen": 15, "mastery": 4},
    "lune":     {"lang": "French",   "lang_color": "#d4812a", "ipa": "lyn",         "gloss": "moon",           "seen": 12, "mastery": 4},
    "merci":    {"lang": "French",   "lang_color": "#d4812a", "ipa": "mɛʁ.si",      "gloss": "thank you",      "seen": 24, "mastery": 5},
    "bonjour":  {"lang": "French",   "lang_color": "#d4812a", "ipa": "bɔ̃.ʒuʁ",     "gloss": "hello",          "seen": 20, "mastery": 5},
    "fleur":    {"lang": "French",   "lang_color": "#d4812a", "ipa": "flœʁ",        "gloss": "flower",         "seen": 7,  "mastery": 3},
    "oiseau":   {"lang": "French",   "lang_color": "#d4812a", "ipa": "wa.zo",       "gloss": "bird",           "seen": 4,  "mastery": 2},
    "ciao":     {"lang": "Italian",  "lang_color": "#3e6534", "ipa": "ˈtʃa.o",      "gloss": "hi / bye",       "seen": 22, "mastery": 5},
    "sole":     {"lang": "Italian",  "lang_color": "#3e6534", "ipa": "ˈso.le",      "gloss": "sun",            "seen": 11, "mastery": 4},
    "pane":     {"lang": "Italian",  "lang_color": "#3e6534", "ipa": "ˈpa.ne",      "gloss": "bread",          "seen": 9,  "mastery": 3},
    "bello":    {"lang": "Italian",  "lang_color": "#3e6534", "ipa": "ˈbɛl.lo",     "gloss": "beautiful",      "seen": 6,  "mastery": 3},
    "libro":    {"lang": "Italian",  "lang_color": "#3e6534", "ipa": "ˈli.bɾo",     "gloss": "book",           "seen": 8,  "mastery": 3},
    "vino":     {"lang": "Italian",  "lang_color": "#3e6534", "ipa": "ˈvi.no",      "gloss": "wine",           "seen": 5,  "mastery": 2},
    "mela":     {"lang": "Italian",  "lang_color": "#3e6534", "ipa": "ˈme.la",      "gloss": "apple",          "seen": 4,  "mastery": 2},
}

# Coordinates are in SVG-space (same system GardenWorld.jsx uses for rendering)
# SVG_TO_PH(x, y) = { x: x+450, y: y+100 } — used internally by Phaser
INITIAL_PLANTS = [
    {"id": "plant-001", "user_id": "u1", "word": "manzana", "x": -260.0, "y":    0.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-002", "user_id": "u1", "word": "casa",    "x": -160.0, "y":  -40.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-003", "user_id": "u1", "word": "agua",    "x": -340.0, "y":   80.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-004", "user_id": "u1", "word": "hola",    "x": -260.0, "y":  140.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-005", "user_id": "u1", "word": "本",       "x":   60.0, "y":  -60.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-006", "user_id": "u1", "word": "りんご",   "x":  180.0, "y":    0.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-007", "user_id": "u1", "word": "猫",       "x":  -20.0, "y":   80.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-008", "user_id": "u1", "word": "Buch",    "x": -300.0, "y":  240.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-009", "user_id": "u1", "word": "Haus",    "x": -200.0, "y":  300.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-010", "user_id": "u1", "word": "soleil",  "x":  -40.0, "y":  280.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-011", "user_id": "u1", "word": "pomme",   "x":   80.0, "y":  220.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-012", "user_id": "u1", "word": "lune",    "x":  140.0, "y":  340.0, "stage": 5, "plot_id": 0, "scale": 1.0},
    {"id": "plant-013", "user_id": "u1", "word": "merci",   "x":  -80.0, "y":  420.0, "stage": 5, "plot_id": 0, "scale": 1.0},
]


def run_seed(db: Session) -> None:
    if db.query(User).count() > 0:
        return

    for u in USERS:
        data = {k: v for k, v in u.items() if not k.startswith("_")}
        if "_demo_password" in u:
            data["password_hash"] = _pwd.hash(u["_demo_password"])
        db.add(User(**data))
    db.flush()

    for word_str, info in WORD_INFO.items():
        db.add(Word(word=word_str, **info))
    db.flush()

    friend_ids = ["u2", "u3", "u4", "u5", "u6", "u7"]
    for fid in friend_ids:
        db.add(Friend(user_id="u1", friend_id=fid))
        db.add(Friend(user_id=fid, friend_id="u1"))
    db.flush()

    for p in INITIAL_PLANTS:
        db.add(GardenPlant(**p))

    db.commit()
    print("[seed] Database seeded successfully.")
