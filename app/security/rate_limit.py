import time

from config import LOGIN_RATE_LIMIT_ATTEMPTS, LOGIN_RATE_LIMIT_WINDOW_SECONDS


_attempts: dict[str, list[float]] = {}


def check_rate_limit(key: str):
    now = time.time()
    window_start = now - LOGIN_RATE_LIMIT_WINDOW_SECONDS
    attempts = [
        attempt_time
        for attempt_time in _attempts.get(key, [])
        if attempt_time >= window_start
    ]

    if len(attempts) >= LOGIN_RATE_LIMIT_ATTEMPTS:
        retry_after = int(LOGIN_RATE_LIMIT_WINDOW_SECONDS - (now - attempts[0]))
        raise ValueError(f"Too many attempts. Try again in {max(1, retry_after)} seconds.")

    attempts.append(now)
    _attempts[key] = attempts


def clear_rate_limit(key: str):
    _attempts.pop(key, None)
