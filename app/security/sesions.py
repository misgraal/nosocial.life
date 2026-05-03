import json
import secrets
import time
from threading import Lock

from config import RUNTIME_DIR


SESSIONS: dict[str, dict] = {}
TTL = 60 * 60 * 24 * 7
SESSIONS_LOCK = Lock()
SESSIONS_FILE = RUNTIME_DIR / "sessions.json"


def ensure_sessions_dir():
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)


def persist_sessions():
    ensure_sessions_dir()
    SESSIONS_FILE.write_text(json.dumps(SESSIONS), encoding="utf-8")


def normalize_session_data(session_data, now: float | None = None) -> dict | None:
    now = now or time.time()
    if isinstance(session_data, (list, tuple)) and len(session_data) >= 2:
        user_id, expires_at = session_data[0], session_data[1]
        return {
            "userID": int(user_id),
            "expiresAt": float(expires_at),
            "createdAt": now,
            "lastSeenAt": now,
            "ip": None,
            "userAgent": None,
        }

    if not isinstance(session_data, dict):
        return None

    user_id = session_data.get("userID")
    expires_at = session_data.get("expiresAt")
    if not user_id or not expires_at:
        return None

    return {
        "userID": int(user_id),
        "expiresAt": float(expires_at),
        "createdAt": float(session_data.get("createdAt") or now),
        "lastSeenAt": float(session_data.get("lastSeenAt") or now),
        "ip": session_data.get("ip"),
        "userAgent": session_data.get("userAgent"),
    }


def load_sessions():
    if not SESSIONS_FILE.exists():
        return

    try:
        raw_sessions = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    now = time.time()
    for session_id, session_data in raw_sessions.items():
        normalized_session = normalize_session_data(session_data, now)
        if not normalized_session or now > normalized_session["expiresAt"]:
            continue
        SESSIONS[session_id] = normalized_session


def cleanup_expired_sessions():
    now = time.time()
    expired_session_ids = [
        session_id
        for session_id, session_data in SESSIONS.items()
        if now > session_data["expiresAt"]
    ]

    for session_id in expired_session_ids:
        SESSIONS.pop(session_id, None)

    if expired_session_ids:
        persist_sessions()


def create_session(user_id: int, ip: str | None = None, user_agent: str | None = None) -> str:
    with SESSIONS_LOCK:
        cleanup_expired_sessions()
        session_id = secrets.token_urlsafe(32)
        now = time.time()
        SESSIONS[session_id] = {
            "userID": user_id,
            "expiresAt": now + TTL,
            "createdAt": now,
            "lastSeenAt": now,
            "ip": ip,
            "userAgent": user_agent,
        }
        persist_sessions()
        return session_id


def get_user_id(session_id: str | None, touch: bool = True) -> int | None:
    if not session_id:
        return None

    with SESSIONS_LOCK:
        cleanup_expired_sessions()
        session_data = SESSIONS.get(session_id)
        if not session_data:
            return None

        if time.time() > session_data["expiresAt"]:
            SESSIONS.pop(session_id, None)
            persist_sessions()
            return None

        if touch:
            session_data["lastSeenAt"] = time.time()
            SESSIONS[session_id] = session_data
            persist_sessions()

        return session_data["userID"]


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
            if session_data["userID"] == user_id
        ]

        for session_id in expired_session_ids:
            SESSIONS.pop(session_id, None)

        if expired_session_ids:
            persist_sessions()


def delete_other_user_sessions(user_id: int, current_session_id: str | None) -> None:
    with SESSIONS_LOCK:
        deleted_session_ids = [
            session_id
            for session_id, session_data in SESSIONS.items()
            if session_data["userID"] == user_id and session_id != current_session_id
        ]

        for session_id in deleted_session_ids:
            SESSIONS.pop(session_id, None)

        if deleted_session_ids:
            persist_sessions()


def list_user_sessions(user_id: int, current_session_id: str | None = None) -> list[dict]:
    with SESSIONS_LOCK:
        cleanup_expired_sessions()
        sessions = []
        now = time.time()
        for session_id, session_data in SESSIONS.items():
            if session_data["userID"] != user_id:
                continue

            sessions.append({
                "sessionID": session_id,
                "current": session_id == current_session_id,
                "createdAt": session_data["createdAt"],
                "lastSeenAt": session_data["lastSeenAt"],
                "expiresInSeconds": max(0, int(session_data["expiresAt"] - now)),
                "ip": session_data.get("ip") or "Unknown",
                "userAgent": session_data.get("userAgent") or "Unknown device",
            })

        sessions.sort(key=lambda session: session["lastSeenAt"], reverse=True)
        return sessions


load_sessions()
