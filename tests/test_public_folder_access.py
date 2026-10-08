import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app.services import folders as folder_service
from app.services import files as file_service
from app.web import folders as folder_web
from app.web import files as file_web


class PublicFolderAccessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = dict(folderID=1, userID=10, publicID="root", public=False,
                         parentFolderID=None, folderName="Root")
        self.public = dict(folderID=2, userID=10, publicID="public", public=True,
                           parentFolderID=1, folderName="Public")
        self.child = dict(folderID=3, userID=10, publicID="child", public=False,
                          parentFolderID=2, folderName="Child")
        self.folders = {1: self.root, 2: self.public, 3: self.child}
        self.file = dict(fileID=4, userID=10, publicID="file", public=False,
                         folderID=3, fileName="example.txt", publicAllowDownload=True)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        path = Path(__file__).resolve()
        self.file["serverPath"] = str(path)
        self.file["sizeBytes"] = path.stat().st_size
        for module in (folder_service, file_service, folder_web, file_web):
            if hasattr(module, "get_folder_by_id"):
                self.stack.enter_context(patch.object(
                    module, "get_folder_by_id", AsyncMock(side_effect=self.folders.get)))
        for module in (file_service, file_web):
            self.stack.enter_context(patch.object(
                module, "get_file_by_public_id", AsyncMock(return_value=self.file)))
            self.stack.enter_context(patch.object(
                module, "is_file_shared_with_user", AsyncMock(return_value=False)))
        self.stack.enter_context(patch.object(
            folder_service, "is_folder_shared_with_user", AsyncMock(return_value=False)))
        self.stack.enter_context(patch.object(file_web, "get_user_id", return_value=20))
        self.stack.enter_context(patch.object(
            file_service, "get_user_file_by_public_id", AsyncMock(return_value=None)))
        self.stack.enter_context(patch.object(
            folder_service, "get_folder_by_public_id", AsyncMock(return_value=self.public)))
        self.stack.enter_context(patch.object(
            folder_service, "get_folders_child_folders",
            AsyncMock(side_effect=lambda fid: [self.child] if fid == 2 else [])))
        for name in ("get_folders_child_files", "get_folders_child_files_for_download"):
            self.stack.enter_context(patch.object(
                folder_service, name,
                AsyncMock(side_effect=lambda fid: [self.file] if fid == 3 else [])))
        self.stack.enter_context(patch.object(
            folder_web, "verify_share_access_token",
            side_effect=lambda item_type, public_id, password_hash, token: token == "valid"))

    def request(self, unlocked=False):
        headers = [(b"cookie", b"share_folder_public=valid")] if unlocked else []
        return Request(dict(type="http", method="GET", path="/", headers=headers))

    async def test_existing_private_files_and_subfolders_are_listed(self):
        self.file["folderID"] = 2
        folder_service.get_folders_child_files.side_effect = lambda fid: [self.file] if fid == 2 else []
        content = await folder_service.get_public_folder_content("public")
        self.assertEqual(content.files, [self.file])
        self.assertEqual(content.folders, [self.child])
        self.assertEqual(len(content.folder_tree["children"]), 1)
        self.assertFalse(self.file["public"])

    async def test_private_file_in_nested_folder_can_be_opened(self):
        file, private = await file_web.get_file_access_context(self.request(), 20, "file")
        self.assertEqual(file, self.file)
        self.assertFalse(private)
        self.assertEqual(await file_service.get_accessible_file(None, "file"), self.file)
        response = await file_web.openFile(self.request(), "file")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template.name, "file_viewer.html")

    async def test_content_and_download_allow_anonymous_access(self):
        file_web.get_user_id.return_value = None
        for handler in (file_web.getFileContent, file_web.downloadFile):
            response = await handler(self.request(), "file")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.path, self.file["serverPath"])

    async def test_folder_password_protects_nested_file(self):
        self.public["publicPasswordHash"] = "hash"
        denied, _ = await file_web.get_file_access_context(self.request(), 20, "file")
        self.assertIsNone(denied)
        allowed, _ = await file_web.get_file_access_context(self.request(True), 20, "file")
        self.assertEqual(allowed, self.file)
        response = await file_web.openFile(self.request(), "file")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/folders/public")

    async def test_disabled_or_expired_folder_revokes_inherited_access(self):
        for settings in (
            dict(public=False),
            dict(public=True, publicExpiresAt=datetime.now() - timedelta(seconds=1)),
        ):
            self.public.update(settings)
            denied, _ = await file_web.get_file_access_context(self.request(True), 20, "file")
            self.assertIsNone(denied)
            with self.assertRaises(HTTPException) as error:
                await file_web.getFileContent(self.request(), "file")
            self.assertEqual(error.exception.status_code, 404)

    async def test_sibling_private_file_does_not_inherit_access(self):
        self.file["folderID"] = 1
        file, _ = await file_web.get_file_access_context(self.request(), 20, "file")
        self.assertIsNone(file)

    async def test_zip_includes_private_descendants_but_respects_download_flag(self):
        _, folders, files = await folder_service.collect_folder_zip_entries(self.public, False)
        self.assertIn("Public/Child", folders)
        self.assertEqual(files[0]["serverPath"], self.file["serverPath"])
        self.file["publicAllowDownload"] = False
        _, _, files = await folder_service.collect_folder_zip_entries(self.public, False)
        self.assertEqual(files, [])
        with self.assertRaises(HTTPException) as error:
            await file_web.downloadFile(self.request(), "file")
        self.assertEqual(error.exception.status_code, 403)

    async def test_owner_still_has_access_to_private_file(self):
        self.public["public"] = False
        file, private = await file_web.get_file_access_context(self.request(), 10, "file")
        self.assertEqual(file, self.file)
        self.assertTrue(private)


if __name__ == "__main__":
    unittest.main()
