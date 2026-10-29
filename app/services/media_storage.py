"""Keep the Movies filesystem tree in step with database folder operations."""

import errno
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from app.db.admin import get_upload_disk_settings
from app.db.files import get_folders_child_files_for_download, update_file_storage_path_db
from app.db.folders import get_folder_by_id, get_folders_child_folders
from config import DISKS, MEDIA_FOLDER_NAME, MEDIA_FOLDER_PUBLIC_ID


logger = logging.getLogger(__name__)


async def get_media_parts(folder_id: int, overrides: dict | None = None) -> tuple[str, ...] | None:
    """Return the physical relative path, stopping at the canonical media root."""
    parts = []
    visited = set()
    while folder_id is not None:
        if folder_id in visited:
            raise ValueError("Folder hierarchy contains a cycle")
        visited.add(folder_id)
        folder = (overrides or {}).get(folder_id) or await get_folder_by_id(folder_id)
        if not folder:
            raise ValueError("Folder was not found")
        if folder.get("publicID") == MEDIA_FOLDER_PUBLIC_ID:
            return (MEDIA_FOLDER_NAME, *reversed(parts))
        name = folder["folderName"]
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("Invalid folder name")
        parts.append(name)
        folder_id = folder["parentFolderID"]
    return None


async def get_storage_roots() -> list[Path]:
    settings = await get_upload_disk_settings()
    paths = [*DISKS, *(row["diskPath"] for row in settings)]
    return sorted({Path(path).resolve() for path in paths}, key=lambda path: len(path.parts), reverse=True)


async def get_media_directories(folder_id: int) -> list[Path]:
    parts = await get_media_parts(folder_id)
    if parts is None or len(parts) == 1:
        return []
    return [_directory(root, parts) for root in await get_storage_roots() if root.is_dir()]


async def create_media_directories(folder_id: int):
    for directory in await get_media_directories(folder_id):
        directory.mkdir(parents=True, exist_ok=True)


def remove_empty_media_directories(directories):
    """Never recursively delete untracked media or the Movies root."""
    for directory in sorted(set(directories), key=lambda path: len(path.parts), reverse=True):
        try:
            directory.rmdir()
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                logger.warning("Could not remove empty media directory %s: %s", directory, error)


def _storage_root(path: Path, roots: list[Path]) -> Path:
    for root in roots:
        if path.is_relative_to(root):
            return root
    raise ValueError("File is outside the configured storage directories")


def _directory(root: Path, parts: tuple[str, ...]) -> Path:
    directory = root.joinpath(*parts)
    if not directory.resolve().is_relative_to(root):
        raise ValueError("Media directory is outside the configured storage directory")
    return directory


@asynccontextmanager
async def sync_media_storage(folder_id: int, *, overrides: dict | None = None, file: dict | None = None):
    """Move physical files before a logical move/rename; undo if that DB write fails.

    Each file stays on its original disk. The destination directories are created
    before moving files so DLNA receives directory and file inotify events.
    """
    old_parts = await get_media_parts(file["folderID"] if file else folder_id)
    new_parts = await get_media_parts(folder_id, overrides)
    if old_parts is None and new_parts is None:
        yield
        return

    roots = await get_storage_roots()
    files = []
    old_directories = []
    new_directories = []

    async def collect(current_id):
        before = await get_media_parts(current_id)
        after = await get_media_parts(current_id, overrides)
        if before and len(before) > 1:
            old_directories.extend(_directory(root, before) for root in roots)
        if after:
            new_directories.extend(_directory(root, after) for root in roots if root.is_dir())
        files.extend((row, after) for row in await get_folders_child_files_for_download(current_id))
        for child in await get_folders_child_folders(current_id):
            await collect(child["folderID"])

    if file:
        files.append((file, new_parts))
    else:
        await collect(folder_id)

    plans = []
    destinations = set()
    for row, parts in files:
        source = Path(row["serverPath"]).resolve()
        root = _storage_root(source, roots)
        destination = _directory(root, parts or ()) / source.name
        if source == destination:
            continue
        if not source.is_file():
            raise ValueError(f"File is missing on disk: {row['fileName']}")
        if destination.exists() or destination in destinations:
            raise ValueError(f"File already exists at destination: {row['fileName']}")
        destinations.add(destination)
        plans.append((row, source, destination))

    moved = []
    created = []
    try:
        for directory in [*new_directories, *(target.parent for _, _, target in plans)]:
            missing = []
            current = directory
            while not current.exists():
                missing.append(current)
                current = current.parent
            directory.mkdir(parents=True, exist_ok=True)
            created.extend(missing)
        for row, source, destination in plans:
            source.rename(destination)
            moved.append((row, source, destination))
            preview = str(destination) if row["previewPath"] == row["serverPath"] else row["previewPath"]
            await update_file_storage_path_db(row["userID"], row["fileID"], str(destination), preview)
        yield
    except BaseException:
        for row, source, destination in reversed(moved):
            try:
                destination.rename(source)
                await update_file_storage_path_db(row["userID"], row["fileID"], row["serverPath"], row["previewPath"])
            except Exception:
                logger.exception("Could not roll back media file move from %s to %s", source, destination)
        remove_empty_media_directories(created)
        raise
    else:
        remove_empty_media_directories(set(old_directories) - set(new_directories))
