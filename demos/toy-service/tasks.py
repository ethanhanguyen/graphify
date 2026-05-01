import time
from models import UserRepository


db = UserRepository("app.db")


def clean_expired_tokens():
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    conn.execute("DELETE FROM tokens WHERE expires_at < datetime('now')")
    conn.commit()
    conn.close()


def run_background_worker(interval: int = 60):
    while True:
        clean_expired_tokens()
        time.sleep(interval)


def _find_inactive_users(days: int = 90) -> list[int]:
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.execute(
        "SELECT id FROM users WHERE last_login < datetime('now', ?)",
        (f"-{days} days",),
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]
