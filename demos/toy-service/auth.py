import hashlib
import secrets
from datetime import datetime, timedelta


SECRET_KEY = secrets.token_hex(32)


def hash_password(password: str) -> str:
    return hashlib.sha256(f"{password}{SECRET_KEY}".encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def validate_token(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = _decode_payload(parts[1])
        if _is_expired(payload):
            return None
        return payload
    except Exception:
        return None


def create_token(user_id: int, email: str) -> str:
    now = datetime.utcnow()
    exp = now + timedelta(hours=24)
    header = _b64_encode('{"alg":"HS256","typ":"JWT"}')
    payload = _b64_encode(f'{{"sub":{user_id},"email":"{email}","exp":{int(exp.timestamp())}}}')
    signature = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{signature}"


def _decode_payload(encoded: str) -> dict:
    import base64
    import json

    return json.loads(base64.urlsafe_b64decode(encoded + "==").decode())


def _is_expired(payload: dict) -> bool:
    exp = payload.get("exp", 0)
    return datetime.utcnow().timestamp() > exp


def _b64_encode(data: str) -> str:
    import base64

    return base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()


def _sign(data: str) -> str:
    return hashlib.sha256(f"{data}{SECRET_KEY}".encode()).hexdigest()
