from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: int
    name: str
    email: str
    role: str = "member"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
        }

    @staticmethod
    def from_db(row: tuple) -> "User":
        return User(id=row[0], name=row[1], email=row[2], role=row[3])


class UserRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def find_by_id(self, user_id: int) -> Optional[User]:
        row = self._query_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if row is None:
            return None
        return User.from_db(row)

    def find_by_email(self, email: str) -> Optional[User]:
        row = self._query_one("SELECT * FROM users WHERE email = ?", (email,))
        if row is None:
            return None
        return User.from_db(row)

    def _query_one(self, sql: str, params: tuple) -> Optional[tuple]:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(sql, params)
        row = cursor.fetchone()
        conn.close()
        return row
