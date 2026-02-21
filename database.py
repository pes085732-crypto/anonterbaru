import json
import os

DB_FILE = "users.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_user(user_id):
    db = load_db()
    return db.get(str(user_id))

def create_user(user_id):
    db = load_db()

    if str(user_id) not in db:
        db[str(user_id)] = {
            "partner": None,
            "gender": None,
            "age": None,
            "location": None,
            "vip": False,
            "karma": 0
        }

    save_db(db)
