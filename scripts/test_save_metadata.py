import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from save_metadata import ARTICLE_TITLE, ISSUE_TITLE, REPOSITORY, SITE_TITLE, RequestError, apply_on_main, request_details, save


class MetadataTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'repo'
        self.article = self.root / 'articles' / '文献 1.html'
        self.article.parent.mkdir(parents=True)
        self.article.write_text('<title>論文</title><meta name="study-category" content="歯科">', encoding='utf-8')
        self.sidecar = self.article.with_name(self.article.name + '.meta.json')
        self.request = {'article': 'articles/文献 1.html', 'category': '疫学', 'tags': ['RCT', 'RCT'],
                        'previous': {'category': '歯科', 'tags': []}}

    def test_publish_and_replay_after_interrupted_deployment(self):
        self.assertEqual(save(self.root, self.request), 'articles/文献 1.html.meta.json')
        self.assertEqual(json.loads(self.sidecar.read_text()), {'category': '疫学', 'tags': ['RCT']})
        self.assertIsNone(save(self.root, self.request))
        self.request['category'] = ''
        self.request['tags'] = []
        with self.assertRaisesRegex(RequestError, '編集中'):
            save(self.root, self.request)
        self.assertEqual(json.loads(self.sidecar.read_text())['category'], '疫学')
        self.request['previous'] = {'category': '疫学', 'tags': ['RCT']}
        save(self.root, self.request)
        self.assertEqual(json.loads(self.sidecar.read_text()), {'category': '', 'tags': []})

    def test_rename_with_inherited_category_and_reset(self):
        original = self.article.read_bytes()
        labels = {'category': '歯科', 'tags': []}
        request = {'article': self.request['article'], **labels, 'title': ' 新しい　題名 ',
                   'previous': {**labels, 'title': ''}}
        save(self.root, request)
        self.assertEqual(json.loads(self.sidecar.read_text()), {'title': '新しい 題名'})
        self.assertEqual(self.article.read_bytes(), original)
        self.assertIsNone(save(self.root, request))

        with self.assertRaisesRegex(RequestError, '編集中'):
            save(self.root, {**request, 'title': '失われる変更'})
        with self.assertRaisesRegex(RequestError, '300文字'):
            save(self.root, {**request, 'title': '題' * 301})
        self.assertEqual(json.loads(self.sidecar.read_text()), {'title': '新しい 題名'})

        save(self.root, self.request)  # a form opened before the title field existed
        self.assertEqual(json.loads(self.sidecar.read_text()),
                         {'category': '疫学', 'tags': ['RCT'], 'title': '新しい 題名'})
        updated_labels = {'category': '疫学', 'tags': ['RCT']}
        reset = {'article': request['article'], **updated_labels, 'title': '',
                 'previous': {**updated_labels, 'title': '新しい 題名'}}
        save(self.root, reset)
        self.assertEqual(json.loads(self.sidecar.read_text()), updated_labels)
        self.assertIsNone(save(self.root, reset))

    def test_limits_and_destination(self):
        for path in ('/articles/文献 1.html', 'articles/../index.html', 'scripts/build.py',
                     'articles/.hidden.html', 'articles/foo/sub.html', 'articles/none.html'):
            with self.subTest(path=path), self.assertRaises(RequestError):
                save(self.root, {**self.request, 'article': path})
        for params in ({'tags': ['x'*61]}, {'tags': list(map(str, range(21)))}, {'category': 'x'*101}):
            with self.subTest(params=params), self.assertRaises(RequestError):
                save(self.root, {**self.request, **params})
        self.sidecar.symlink_to(self.article)
        with self.assertRaises(RequestError):
            save(self.root, self.request)

    def test_source_identity(self):
        event = {'action': 'opened', 'repository': {'full_name': REPOSITORY},
                 'sender': {'login': 'mxe050'}, 'issue': {'title': ISSUE_TITLE, 'user': {'login': 'mxe050'},
                                                        'body': json.dumps(self.request)}}
        self.assertEqual(request_details(event), self.request)
        for change in ({'sender': {'login': 'reader'}}, {'issue': {**event['issue'], 'user': {'login': 'reader'}}},
                       {'repository': {'full_name': 'reader/archive'}}, {'action': 'edited'}):
            with self.subTest(change=change), self.assertRaises(RequestError):
                request_details({**event, **change})

    def test_site_and_article_issue_routes_require_matching_shape_and_owner(self):
        def event(topic, payload, sender='mxe050'):
            return {'action': 'opened', 'repository': {'full_name': REPOSITORY},
                    'sender': {'login': sender}, 'issue': {'title': topic, 'user': {'login': 'mxe050'},
                                                          'body': json.dumps(payload)}}

        article = {**self.request, 'title': '新しいタイトル',
                   'previous': {**self.request['previous'], 'title': ''}}
        site = {'siteTitle': '新しい書斎名', 'previous': {'siteTitle': 'Y先生文献の書斎'}}
        for topic, payload in ((ARTICLE_TITLE, article), (SITE_TITLE, site)):
            self.assertEqual(request_details(event(topic, payload)), payload)
            with self.assertRaises(RequestError):
                request_details(event(topic, payload, sender='reader'))
        for topic, payload in ((ISSUE_TITLE, article), (ARTICLE_TITLE, self.request),
                               (ARTICLE_TITLE, site), (SITE_TITLE, article),
                               (ARTICLE_TITLE, {**article, 'previous': self.request['previous']})):
            with self.subTest(topic=topic, payload=payload), self.assertRaises(RequestError):
                request_details(event(topic, payload))

    def test_git_update_keeps_the_uploaded_html(self):
        def git(*args, cwd=None):
            return subprocess.check_output(['git', *args], cwd=cwd or self.root, stderr=subprocess.STDOUT)

        remote = self.root.parent / 'upstream.git'
        git('init', '--bare', '-b', 'main', str(remote))
        git('init', '-b', 'main')
        git('add', 'articles')
        git('-c', 'user.name=test', '-c', 'user.email=test@localhost', 'commit', '-m', 'Upload')
        git('remote', 'add', 'origin', str(remote))
        git('push', 'origin', 'main')
        original = git('show', 'main:articles/文献 1.html')
        apply_on_main(self.root, self.request)
        first = git('rev-parse', 'main', cwd=remote)
        self.assertEqual(git('show', 'main:articles/文献 1.html', cwd=remote), original)
        self.assertEqual(json.loads(git('show', 'main:articles/文献 1.html.meta.json', cwd=remote))['category'], '疫学')
        apply_on_main(self.root, self.request)
        self.assertEqual(git('rev-parse', 'main', cwd=remote), first)

        change = {'siteTitle': '研究の書斎', 'previous': {'siteTitle': 'Y先生文献の書斎'}}
        apply_on_main(self.root, change)
        self.assertEqual(json.loads(git('show', 'main:site-settings.json', cwd=remote)), {'title': '研究の書斎'})
        self.assertEqual(git('show', 'main:articles/文献 1.html', cwd=remote), original)
        with self.assertRaisesRegex(RequestError, '編集中'):
            apply_on_main(self.root, {**change, 'siteTitle': '古い画面からの変更'})


if __name__ == '__main__':
    unittest.main()
