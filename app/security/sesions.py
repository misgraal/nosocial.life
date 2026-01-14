# app/security/sessions.py
import time
import secrets

SESSIONS: dict[str, tuple[int, float]] = {}  # session_id -> (user_id, expires_at)
TTL = 60 * 60 * 24 * 7  # 7 days

def create_session(user_id: int) -> str:
    session_id = secrets.token_urlsafe(32)
    SESSIONS[session_id] = (user_id, time.time() + TTL)
    return session_id

def get_user_id(session_id: str | None) -> int | None:
    if not session_id:
        return None
    data = SESSIONS.get(session_id)
    if not data:
        return None
    user_id, expires = data
    if time.time() > expires:
        SESSIONS.pop(session_id, None)
        return None
    return user_id

def delete_session(session_id: str | None) -> None:
    if session_id:
        SESSIONS.pop(session_id, None)
