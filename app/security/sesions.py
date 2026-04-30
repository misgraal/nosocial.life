import json
import secrets
import time
from pathlib import Path
from threading import Lock


SESSIONS: dict[str, tuple[int, float]] = {}
TTL = 60 * 60 * 24 * 7
SESSIONS_LOCK = Lock()
SESSIONS_FILE = Path(__file__).resolve().parents[2] / "runtime" / "sessions.json"


def ensure_sessions_dir():
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)


def persist_sessions():
    ensure_sessions_dir()
    serializable_sessions = {
        session_id: {
            "userID": user_id,
            "expiresAt": expires_at
        }
        for session_id, (user_id, expires_at) in SESSIONS.items()
    }
    SESSIONS_FILE.write_text(json.dumps(serializable_sessions), encoding="utf-8")


def load_sessions():
    if not SESSIONS_FILE.exists():
        return

    try:
        raw_sessions = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    now = time.time()
    for session_id, session_data in raw_sessions.items():
        user_id = session_data.get("userID")
        expires_at = session_data.get("expiresAt")
        if not user_id or not expires_at or now > float(expires_at):
            continue
        SESSIONS[session_id] = (int(user_id), float(expires_at))


def cleanup_expired_sessions():
    now = time.time()
    expired_session_ids = [
        session_id
        for session_id, (_, expires_at) in SESSIONS.items()
        if now > expires_at
    ]

    for session_id in expired_session_ids:
        SESSIONS.pop(session_id, None)

    if expired_session_ids:
        persist_sessions()


def create_session(user_id: int) -> str:
    with SESSIONS_LOCK:
        cleanup_expired_sessions()
        session_id = secrets.token_urlsafe(32)
        SESSIONS[session_id] = (user_id, time.time() + TTL)
        persist_sessions()
        return session_id


def get_user_id(session_id: str | None) -> int | None:
    if not session_id:
        return None

    with SESSIONS_LOCK:
        cleanup_expired_sessions()
        session_data = SESSIONS.get(session_id)
        if not session_data:
            return None

        user_id, expires_at = session_data
        if time.time() > expires_at:
            SESSIONS.pop(session_id, None)
            persist_sessions()
            return None

        return user_id


def delete_session(session_id: str | None) -> None:
    if not session_id:
        return

    with SESSIONS_LOCK:
        if session_id in SESSIONS:
            SESSIONS.pop(session_id, None)
            persist_sessions()


def delete_user_sessions(user_id: int) -> None:
    with SESSIONS_LOCK:
        expired_session_ids = [
            session_id
            for session_id, session_data in SESSIONS.items()
            if session_data[0] == user_id
        ]

        for session_id in expired_session_ids:
            SESSIONS.pop(session_id, None)

        if expired_session_ids:
            persist_sessions()


load_sessions()
