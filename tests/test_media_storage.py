import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services import app as drive
from app.services import files as file_service
from app.services import folders as folder_service
from app.services import media_storage as storage


class MediaStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.folders = {
            1: dict(folderID=1, userID=1, folderName="User", parentFolderID=None, publicID="home"),
            2: dict(folderID=2, userID=1, folderName="Movies", parentFolderID=1, publicID="movies"),
            3: dict(folderID=3, userID=1, folderName="Series", parentFolderID=2, publicID="series"),
            4: dict(folderID=4, userID=2, folderName="Season", parentFolderID=3, publicID="season"),
            5: dict(folderID=5, userID=1, folderName="Private", parentFolderID=1, publicID="private"),
        }
        self.files = {}
        self.stack.enter_context(patch.object(storage, "DISKS", [str(self.root)]))
        self.stack.enter_context(patch.object(storage, "get_upload_disk_settings", AsyncMock(return_value=[])))
        self.stack.enter_context(patch.object(
            storage, "get_folder_by_id", AsyncMock(side_effect=lambda fid: dict(self.folders[fid]))))
        self.stack.enter_context(patch.object(storage, "get_folders_child_folders", AsyncMock(
            side_effect=lambda fid: [dict(f) for f in self.folders.values() if f["parentFolderID"] == fid])))
        self.stack.enter_context(patch.object(storage, "get_folders_child_files_for_download", AsyncMock(
            side_effect=lambda fid: [dict(f) for f in self.files.values() if f["folderID"] == fid])))
        self.write_path = self.stack.enter_context(patch.object(
            storage, "update_file_storage_path_db", AsyncMock(side_effect=self.update_path)))

    async def update_path(self, user_id, file_id, path, preview):
        self.assertEqual(self.files[file_id]["userID"], user_id)
        self.files[file_id].update(serverPath=path, previewPath=preview)

    def add_file(self, file_id=10, folder_id=4, relative="Movies/Series/Season/episode.mp4", owner=2):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"media-content")
        self.files[file_id] = dict(fileID=file_id, userID=owner, folderID=folder_id,
                                   fileName=path.name, serverPath=str(path), previewPath=str(path),
                                   publicID=f"file-{file_id}")
        return path

    async def test_create_folder_makes_physical_directory(self):
        self.stack.enter_context(patch.object(folder_service, "get_folder_by_public_id", AsyncMock(return_value=self.folders[2])))
        self.stack.enter_context(patch.object(folder_service, "check_dublicate", AsyncMock(return_value=0)))
        self.stack.enter_context(patch.object(folder_service, "create_folder_db", AsyncMock(return_value=self.folders[3])))
        self.stack.enter_context(patch.object(folder_service, "get_folder_id_by_public_id", AsyncMock(return_value=dict(folderID=3))))
        self.stack.enter_context(patch.object(folder_service, "get_folder_by_id", AsyncMock(return_value=self.folders[2])))
        self.stack.enter_context(patch.object(folder_service, "is_media_folder", AsyncMock(return_value=True)))
        self.stack.enter_context(patch.object(folder_service, "update_folder_public_db", AsyncMock(return_value=self.folders[3])))
        self.stack.enter_context(patch.object(folder_service, "create_audit_log", AsyncMock()))
        await folder_service.create_folder("Series", 1, "/app/folders/movies")
        self.assertTrue((self.root / "Movies/Series").is_dir())

    async def test_move_existing_private_folder_into_movies_moves_nested_files(self):
        self.folders[3]["parentFolderID"] = 5
        source = self.add_file(relative="episode.mp4")
        changed = {**self.folders[3], "parentFolderID": 2}
        async with storage.sync_media_storage(3, overrides={3: changed}):
            self.folders[3] = changed
        destination = self.root / "Movies/Series/Season/episode.mp4"
        self.assertFalse(source.exists())
        self.assertEqual(destination.read_bytes(), b"media-content")
        self.assertEqual(self.files[10]["serverPath"], str(destination))
        self.assertEqual(self.files[10]["previewPath"], str(destination))

    async def test_reconcile_existing_media_folder_repairs_legacy_paths(self):
        source = self.add_file(relative="episode.mp4")
        async with storage.sync_media_storage(3):
            pass
        self.assertFalse(source.exists())
        self.assertTrue((self.root / "Movies/Series/Season/episode.mp4").is_file())

    async def test_folder_rename_moves_files_and_removes_old_directories(self):
        source = self.add_file()
        changed = {**self.folders[3], "folderName": "Renamed"}
        async with storage.sync_media_storage(3, overrides={3: changed}):
            self.folders[3] = changed
        self.assertFalse(source.exists())
        self.assertFalse((self.root / "Movies/Series").exists())
        self.assertTrue((self.root / "Movies/Renamed/Season/episode.mp4").is_file())
        self.assertTrue((self.root / "Movies").is_dir())

    async def test_move_out_of_movies_removes_media_files_from_dlna_tree(self):
        source = self.add_file()
        changed = {**self.folders[3], "parentFolderID": 5}
        async with storage.sync_media_storage(3, overrides={3: changed}):
            self.folders[3] = changed
        self.assertFalse(source.exists())
        self.assertFalse((self.root / "Movies/Series").exists())
        self.assertEqual(self.files[10]["serverPath"], str(self.root / "episode.mp4"))
        self.assertTrue((self.root / "episode.mp4").is_file())

    async def test_move_file_service_updates_physical_path_and_logical_parent(self):
        source = self.add_file(folder_id=5, relative="episode.mp4", owner=1)
        for name, mock in {
            "get_all_user_folders": AsyncMock(return_value=list(self.folders.values())),
            "get_folder_by_public_id": AsyncMock(return_value=self.folders[2]),
            "get_user_file_by_public_id": AsyncMock(side_effect=lambda uid, pid: dict(self.files[10])),
            "get_user_file_by_name_in_folder": AsyncMock(return_value=None),
            "update_file_folder_db": AsyncMock(),
            "update_file_public_db": AsyncMock(),
            "create_audit_log": AsyncMock(),
        }.items():
            self.stack.enter_context(patch.object(drive, name, mock))
        await drive.move_items(1, drive.MoveItemsPayload([], ["file-10"], "series"))
        self.assertFalse(source.exists())
        self.assertTrue((self.root / "Movies/Series/episode.mp4").is_file())
        drive.update_file_folder_db.assert_awaited_once_with(1, 10, 3)

    async def test_destination_collision_preserves_both_files(self):
        source = self.add_file(folder_id=5, relative="episode.mp4")
        destination = self.root / "Movies/Series/episode.mp4"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"existing-content")
        with self.assertRaisesRegex(ValueError, "already exists"):
            async with storage.sync_media_storage(3, file=dict(self.files[10])):
                self.fail("A conflicting move must not reach the logical update")
        self.assertEqual(source.read_bytes(), b"media-content")
        self.assertEqual(destination.read_bytes(), b"existing-content")
        self.write_path.assert_not_awaited()

    async def test_logical_database_failure_rolls_back_file_and_path(self):
        source = self.add_file()
        changed = {**self.folders[3], "folderName": "Renamed"}
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            async with storage.sync_media_storage(3, overrides={3: changed}):
                raise RuntimeError("database unavailable")
        self.assertTrue(source.is_file())
        self.assertEqual(self.files[10]["serverPath"], str(source))
        self.assertFalse((self.root / "Movies/Renamed").exists())

    async def test_path_update_failure_rolls_back_all_moved_files(self):
        first = self.add_file()
        second = self.add_file(file_id=11, relative="Movies/Series/Season/second.mp4")
        async def fail_second(uid, fid, path, preview):
            if fid == 11 and "Renamed" in path:
                raise RuntimeError("path write failed")
            await self.update_path(uid, fid, path, preview)
        self.write_path.side_effect = fail_second
        changed = {**self.folders[3], "folderName": "Renamed"}
        with self.assertRaisesRegex(RuntimeError, "path write failed"):
            async with storage.sync_media_storage(3, overrides={3: changed}):
                self.fail("An incomplete move must not reach the logical update")
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertEqual(self.files[10]["serverPath"], str(first))
        self.assertFalse((self.root / "Movies/Renamed").exists())

    async def test_cleanup_keeps_untracked_media(self):
        self.add_file()
        untracked = self.root / "Movies/Series/Season/untracked.mp4"
        untracked.write_bytes(b"untracked")
        changed = {**self.folders[3], "folderName": "Renamed"}
        async with storage.sync_media_storage(3, overrides={3: changed}):
            self.folders[3] = changed
        self.assertEqual(untracked.read_bytes(), b"untracked")

    async def test_delete_folder_removes_physical_tree_and_uses_actual_file_owners(self):
        source = self.add_file()
        for name, mock in {
            "get_user_folder_by_public_id": AsyncMock(return_value=self.folders[3]),
            "get_folder_by_id": AsyncMock(side_effect=lambda fid: dict(self.folders[fid])),
            "collect_folder_delete_data": AsyncMock(return_value=([3, 4], [dict(self.files[10])])),
            "delete_file_db": AsyncMock(),
            "delete_folder_db": AsyncMock(),
            "create_audit_log": AsyncMock(),
        }.items():
            self.stack.enter_context(patch.object(file_service, name, mock))
        await file_service.delete_items(1, drive.DeleteItemsPayload(["series"], []))
        self.assertFalse(source.exists())
        self.assertFalse((self.root / "Movies/Series").exists())
        self.assertTrue((self.root / "Movies").is_dir())
        file_service.delete_file_db.assert_awaited_once_with(2, 10)
        self.assertEqual(file_service.delete_folder_db.await_args_list[0].args, (2, 4))

    async def test_media_directory_symlink_cannot_escape_storage(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "Movies").mkdir()
            (self.root / "Movies/Series").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "outside"):
                await storage.create_media_directories(3)
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
