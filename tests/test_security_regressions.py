import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request
from app.security.share_tokens import create_share_token, verify_share_token
from app.services import files as service
from app.services.app import UploadChunkPayload
from app.web import files as web
from app.web.folders import has_valid_folder_share_cookie


def request(user=None):
    cookie = b'session_id=test' if user else b''
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': [(b'cookie', cookie)]})


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.item = dict(publicID='abc', userID=1, fileID=2, folderID=3,
                         public=True, publicPasswordHash='password-hash',
                         publicExpiresAt=None, publicAllowDownload=False,
                         fileName='test.html', serverPath='/missing')

    def test_share_tokens(self):
        token = create_share_token('file', self.item)
        self.assertTrue(verify_share_token(token, 'file', self.item))
        for invalid in ['1', '', token + 'x', '0.bad']:
            self.assertFalse(verify_share_token(invalid, 'file', self.item))
        self.assertFalse(verify_share_token(token, 'folder', self.item))
        self.assertFalse(verify_share_token(token, 'file', dict(self.item, publicID='other')))
        self.assertFalse(verify_share_token(token, 'file', dict(self.item, publicPasswordHash='changed')))
        with patch('app.security.share_tokens.time.time', return_value=10**12):
            self.assertFalse(verify_share_token(token, 'file', self.item))
        self.assertFalse(web.has_valid_file_share_cookie(SimpleNamespace(cookies={'share_file_abc':'1'}), self.item))
        self.assertFalse(has_valid_folder_share_cookie(SimpleNamespace(cookies={'share_folder_abc':'1'}), self.item))

    async def test_public_link_is_not_private_access(self):
        with patch.multiple(service, get_user_file_by_public_id=AsyncMock(return_value=None),
                            get_file_by_public_id=AsyncMock(return_value=self.item),
                            is_file_shared_with_user=AsyncMock(return_value=False),
                            get_folder_by_id=AsyncMock(return_value=None),
                            can_user_access_shared_folder=AsyncMock(return_value=False)):
            self.assertIsNone(await service.get_accessible_file(99, 'abc'))
        with patch.object(service, 'get_user_file_by_public_id', AsyncMock(return_value=self.item)):
            self.assertEqual(await service.get_accessible_file(1, 'abc'), self.item)

    async def test_locked_public_endpoints_reject_logged_in_stranger(self):
        with patch.object(web, 'get_user_id', return_value=99), \
             patch.object(web, 'get_accessible_file', AsyncMock(return_value=None)), \
             patch.object(web, 'get_file_by_public_id', AsyncMock(return_value=self.item)):
            for endpoint in [web.getFileContent, web.getFileThumbnail, web.getFilePreview, web.downloadFile]:
                with self.assertRaises(HTTPException) as error:
                    await endpoint(request(True), 'abc')
                self.assertEqual(error.exception.status_code, 404)
            self.item['publicPasswordHash'] = None
            with self.assertRaises(HTTPException) as error:
                await web.downloadFile(request(True), 'abc')
            self.assertEqual(error.exception.status_code, 403)

    async def test_uploaded_active_content_is_sandboxed(self):
        with tempfile.NamedTemporaryFile(suffix='.html') as handle:
            self.item['serverPath'] = handle.name
            with patch.object(web, 'get_user_id', return_value=1), \
                 patch.object(web, 'get_accessible_file', AsyncMock(return_value=self.item)):
                response = await web.getFileContent(request(True), 'abc')
                self.assertIn('sandbox;', response.headers['content-security-policy'])
                self.assertNotIn('allow-scripts', response.headers['content-security-policy'])
                self.assertEqual(response.headers['x-content-type-options'], 'nosniff')

    async def test_upload_namespaces_survive_memory_reset(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(service, 'DISKS', [directory]), \
             patch.object(service, 'get_enabled_upload_disks', AsyncMock(return_value=[directory])), \
             patch.object(service, 'upload_list', []), \
             patch.object(service, 'cancelled_upload_ids', set()), \
             patch.object(service, 'cleanup_stale_upload_chunks', AsyncMock()), \
             patch.object(service, 'select_upload_disk', AsyncMock(return_value=directory)):
            payload = UploadChunkPayload('same', 'a.txt', 'text/plain', 4, 0, 2, 2, False, '/', chunk_start=0)
            await service.handle_chunk_upload(1, payload, b'ab')
            await service.handle_chunk_upload(2, payload, b'cd')
            first = Path(directory) / Path(service.tmpFolder).name / 'chunks' / '1_same' / 'upload.data'
            second = first.parent.parent / '2_same' / 'upload.data'
            self.assertEqual(first.read_bytes(), b'ab')
            self.assertEqual(second.read_bytes(), b'cd')
            service.upload_list.clear()
            self.assertFalse((await service.get_upload_status(3, 'same'))['exists'])
            await service.cancel_upload(2, 'same')
            self.assertTrue((await service.get_upload_status(1, 'same'))['exists'])
            await service.cancel_upload(1, 'same')
            self.assertFalse((await service.get_upload_status(1, 'same'))['exists'])

    async def test_legacy_upload_rejects_false_size_before_db_write(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(service, 'cleanup_stale_upload_chunks', AsyncMock()), \
             patch.object(service, 'select_upload_disk', AsyncMock(return_value=directory)), \
             patch.object(service, 'upload_list', []), \
             patch.object(service, 'cancelled_upload_ids', set()), \
             patch.object(service, 'create_file_db', AsyncMock()) as create:
            payload = UploadChunkPayload('size-test', 'a.txt', 'text/plain', 1, 0, 1, 4, True, '/')
            with self.assertRaisesRegex(ValueError, 'Final file size mismatch'):
                await service.handle_chunk_upload(1, payload, b'abcd')
            create.assert_not_awaited()

    async def test_upload_destination_requires_ownership(self):
        with patch.object(service, 'get_user_folder_by_public_id', AsyncMock(return_value=None)):
            with self.assertRaisesRegex(ValueError, 'Folder was not found'):
                await service.resolve_upload_folder_id(99, 'someone-elses-folder')

    async def test_explicit_recipient_keeps_private_access(self):
        with patch.multiple(service, get_user_file_by_public_id=AsyncMock(return_value=None),
                            get_file_by_public_id=AsyncMock(return_value=self.item),
                            is_file_shared_with_user=AsyncMock(return_value=True)):
            self.assertEqual(await service.get_accessible_file(99, 'abc'), self.item)
