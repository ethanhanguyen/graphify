from models import User, UserRepository
from auth import create_token, hash_password, validate_token, verify_password


db = UserRepository("app.db")


def get_user(user_id: int, token: str) -> dict | None:
    payload = validate_token(token)
    if payload is None:
        return None
    user = db.find_by_id(user_id)
    if user is None:
        return None
    return user.to_dict()


def create_user(name: str, email: str, password: str) -> dict:
    hashed = hash_password(password)
    new_id = _insert_user(name, email, hashed)
    token = create_token(new_id, email)
    return {"id": new_id, "name": name, "email": email, "token": token}


def authenticate(email: str, password: str) -> dict | None:
    user = db.find_by_email(email)
    if user is None:
        return None
    if not verify_password(password, _get_hashed_password(user.id)):
        return None
    token = create_token(user.id, email)
    return {"user": user.to_dict(), "token": token}


def _insert_user(name: str, email: str, password_hash: str) -> int:
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.execute(
        "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
        (name, email, password_hash),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def _get_hashed_password(user_id: int) -> str:
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.execute("SELECT password FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""
