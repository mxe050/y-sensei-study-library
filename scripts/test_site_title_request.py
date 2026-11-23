import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from site_settings import DEFAULT_TITLE
from site_title_request import SiteTitleError, save_site_title


class ShelfRenameTests(unittest.TestCase):
    def test_create_rename_replay_and_stale_request(self):
        with TemporaryDirectory() as work:
            root = Path(work)
            request = {'siteTitle': '私の & 書斎', 'previous': {'siteTitle': DEFAULT_TITLE}}
            name = save_site_title(root, request)
            self.assertEqual(json.loads((root / name).read_text()), {'title': request['siteTitle']})
            self.assertIsNone(save_site_title(root, request))
            with self.assertRaises(SiteTitleError):
                save_site_title(root, {**request, 'siteTitle': '別の名前'})
            self.assertEqual(json.loads((root / name).read_text())['title'], request['siteTitle'])

    def test_reject_invalid_title_before_writing(self):
        with TemporaryDirectory() as work:
            root = Path(work)
            for name in (' ', 'あ' * 81, 18, None):
                with self.subTest(name=name), self.assertRaises(SiteTitleError):
                    save_site_title(root, {'siteTitle': name, 'previous': {'siteTitle': DEFAULT_TITLE}})
            self.assertFalse((root / 'site-settings.json').exists())
