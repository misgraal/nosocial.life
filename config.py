import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"
RUNTIME_DIR = BASE_DIR / "runtime"


def _system_name() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "win"
    return "linux"


system = _system_name()


def _resolve_path(path_value: str) -> str:
    path = Path(os.path.expandvars(os.path.expanduser(path_value.strip())))
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path)


def _split_storage_dirs(value: str) -> list[str]:
    separator = "," if "," in value else os.pathsep
    return [
        _resolve_path(part)
        for part in value.split(separator)
        if part.strip()
    ]


def _default_storage_dirs() -> list[str]:
    if system == "linux":
        return ["/mnt/storage"]
    if system == "win":
        return ["H:/"]
    return [str(BASE_DIR / "files")]


DISKS = _split_storage_dirs(os.getenv("NOSOCIAL_STORAGE_DIRS", "")) or _default_storage_dirs()

TMP_FOLDER = os.getenv("NOSOCIAL_TMP_FOLDER", "temp")
tmpFolder = TMP_FOLDER
MEDIA_FOLDER_NAME = os.getenv("NOSOCIAL_MEDIA_FOLDER", "Movies")
MEDIA_FOLDER_PUBLIC_ID = os.getenv("NOSOCIAL_MEDIA_FOLDER_PUBLIC_ID", "movies")
COOKIE_SECURE = os.getenv("NOSOCIAL_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
LOGIN_RATE_LIMIT_ATTEMPTS = int(os.getenv("NOSOCIAL_LOGIN_RATE_LIMIT_ATTEMPTS", "8"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("NOSOCIAL_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))
