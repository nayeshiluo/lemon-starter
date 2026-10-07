import asyncio
import os
import pathlib
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch


class IsolatedTelegramTemplate(unittest.TestCase):
    def load_template(self, env):
        root = pathlib.Path(__file__).resolve().parents[1]
        with tarfile.open(root / 'skills_bundle.tar.gz') as archive:
            code = archive.extractfile('skills/media/telegram-media-harvester/scripts/isolated_tg.py').read()
        class Client:
            def __init__(self, session, api_id, api_hash):
                self.args = session, api_id, api_hash
                self.connected = False
            async def connect(self): self.connected = True
            async def disconnect(self): self.connected = False
        telethon = types.ModuleType('telethon')
        telethon.TelegramClient = Client
        namespace = {}
        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {'telethon': telethon}):
            exec(compile(code, 'isolated_tg.py', 'exec'), namespace)
        return namespace['IsolatedTelegramClient']

    def test_runtime_credentials_session_copy_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            original = pathlib.Path(temp) / 'original.session'
            original.write_bytes(b'fixture session')
            value = 'ab' * 16
            template = self.load_template({'TG_API_ID': '12345', 'TG_API_HASH': value,
                                           'TG_SESSION_PATH': str(original)})
            context = template()
            context.temp_session_name = str(pathlib.Path(temp) / 'isolated')
            context.session_file = context.temp_session_name + '.session'
            async def exercise():
                async with context as client:
                    self.assertEqual(client.args, (context.temp_session_name, 12345, value))
                    self.assertTrue(client.connected)
                    self.assertEqual(pathlib.Path(context.session_file).read_bytes(), original.read_bytes())
                    pathlib.Path(context.temp_session_name + '.session-journal').write_bytes(b'journal')
                self.assertFalse(client.connected)
            asyncio.run(exercise())
            self.assertFalse(pathlib.Path(context.session_file).exists())
            self.assertFalse(pathlib.Path(context.temp_session_name + '.session-journal').exists())
            self.assertEqual(original.read_bytes(), b'fixture session')

    def test_missing_credentials_fail_before_copy(self):
        context = self.load_template({})()
        with patch('shutil.copyfile') as copy:
            with self.assertRaisesRegex(ValueError, 'TG_API_ID and TG_API_HASH'):
                asyncio.run(context.__aenter__())
            copy.assert_not_called()


if __name__ == '__main__': unittest.main()
