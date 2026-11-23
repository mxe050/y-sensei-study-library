import json
from html import unescape
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, quote, urljoin, urlsplit

from build import build, ROOT, SITE_FILES


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.out = Path(self.temp.name) / 'published'
        (self.root / 'articles').mkdir(parents=True)
        for name in SITE_FILES:
            self.add(name, (ROOT / name).read_bytes())

    def add(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return path

    def test_site_rename_updates_pages_and_reader_while_preserving_article(self):
        name = 'articles/2026/index.html'
        original = '<title>原文のタイトル</title><h1>Y先生文献の書斎</h1>'
        article = self.add(name, original)
        build(self.root, self.out / 'original')
        default = (self.out / 'original/index.html').read_text()
        self.assertIn('<span>Y先生</span><strong>文献の書斎</strong>', default)

        self.add('site-settings.json', json.dumps({'title': '  臨床 & 統計  <文献>  '}))
        build(self.root, self.out / 'updated')
        index = (self.out / 'updated/index.html').read_text()
        manage = (self.out / 'updated/manage.html').read_text()
        reader = (self.out / 'updated' / name).read_text()
        safe = '臨床 &amp; 統計 &lt;文献&gt;'
        for phrase in (f'<title>{safe}</title>', f'</span>{safe}</a>',
                       f'<strong>{safe}</strong>', f'<span>{safe}</span>'):
            self.assertIn(phrase, index)
        self.assertIn('Y先生が批判的吟味をした論文集です。', index)
        self.assertIn(f'｜{safe}</title>', manage)
        self.assertIn(f'{safe}</a>', manage)
        self.assertIn(f'← {safe}へ</a>', reader)
        self.assertIn('<title>原文のタイトル</title>', reader)
        self.assertIn('<h1>Y先生文献の書斎</h1>', reader)
        self.assertEqual(article.read_text(), original)
        self.assertEqual(json.loads((self.out / 'updated/site-settings.json').read_text()),
                         {'title': '臨床 & 統計 <文献>'})
        self.assertNotEqual((self.out / 'original/catalog-version.json').read_text(),
                            (self.out / 'updated/catalog-version.json').read_text())

    def test_empty_shelf_omits_unpublished_files(self):
        self.add('notes.json', 'private-only fixture')
        self.add('articles/.gitkeep', b'')
        self.assertEqual(build(self.root, self.out), [])
        self.assertFalse((self.out / 'notes.json').exists())
        self.assertFalse((self.out / 'articles/.gitkeep').exists())
        page = (self.out / 'index.html').read_text()
        self.assertIn('>0件</p>', page)
        self.assertNotIn('data-empty-state hidden', page)
        header = page.split('</header>', 1)[0]
        self.assertIn('href="./manage.html">掲載・編集</a>', header)

    def test_catalog_is_rendered_before_scripts_run_and_matches_editor(self):
        filename = 'articles/Gormley2026_象牙質知覚過敏_統合解説.html'
        self.add(filename, '<title>論文 &amp; &lt;要旨&gt;</title>'
                 '<meta name="description" content="&lt;/script&gt;">'
                 '<meta name="study-category" content="歯科">'
                 '<meta name="study-tags" content="知覚過敏、NMA; 知覚過敏">')
        entries = build(self.root, self.out)
        index = (self.out / 'index.html').read_text()
        version = json.loads((self.out / 'catalog-version.json').read_text())['version']
        self.assertIn(f'<meta name="catalog-version" content="{version}">', index)
        self.assertIn('>1件</p>', index)
        self.assertIn('data-empty-state hidden', index)
        self.assertIn(f'data-article-id="{filename}"', index)
        self.assertIn(f'href="{entries[0]["path"]}"', index)
        self.assertIn('<h3>論文 &amp; &lt;要旨&gt;</h3>', index)
        self.assertIn('<li>知覚過敏</li><li>NMA</li>', index)
        self.assertEqual(entries[0]['tags'], ['知覚過敏', 'NMA'])
        for name in ('index.html', 'manage.html'):
            page = (self.out / name).read_text()
            payload = re.search(r'<script type="application/json" id="catalog-data">(.*?)</script>', page, re.S)
            self.assertEqual(json.loads(payload[1]), entries)
            self.assertNotIn('/catalog-data.js', page)
            self.assertRegex(page, r'(?:catalog|manage)\.js\?v=[a-f0-9]{12}')

    def test_sidecar_overrides_and_clears_fields_without_modifying_source(self):
        original = '<h1>解説</h1><meta name="study-category" content="歯科"><meta name="keywords" content="A,B">'
        name = 'articles/智歯/index.htm'
        article = self.add(name, original)
        def read_at(stage):
            return build(self.root, self.out / stage)[0]
        first = read_at('first')
        self.assertEqual(first['tags'], ['A', 'B'])
        self.assertFalse(first['hasMetadata'])
        self.assertEqual(first['metadataFields'], [])
        self.add(name + '.meta.json', '{"category":"  口腔外科 ","tags":["RCT"," A & B ","RCT"]}')
        edited = read_at('edited')
        self.assertTrue(edited['hasMetadata'])
        self.assertEqual(edited['metadataFields'], ['category', 'tags'])
        self.assertEqual((edited['category'], edited['tags']), ('口腔外科', ['RCT', 'A & B']))
        self.assertEqual(edited['path'], first['path'])
        self.assertNotEqual((self.out / 'first/catalog-version.json').read_text(),
                            (self.out / 'edited/catalog-version.json').read_text())
        self.add(name + '.meta.json', '{"category":"","tags":[]}')
        cleared = read_at('cleared')
        self.assertEqual((cleared['category'], cleared['tags']), ('未分類', []))
        self.add(name + '.meta.json', '{"tags":["Open access"]}')
        partial = read_at('partial')
        self.assertEqual((partial['category'], partial['tags']), ('歯科', ['Open access']))
        self.assertEqual(article.read_text(), original)

    def test_images_and_article_bytes_preserved_with_return_navigation(self):
        name = 'articles/智歯 1/index.html'
        source = ('<!DOCTYPE html>\r\n<html lang="ja"><head><title>歯 &amp; 顎</title>'
                  '<meta name="description" content="&lt;/script&gt;">'
                  '<meta name="study-category" content="口腔外科"></head>\r\n'
                  '<body\n class="test"><h1>解説</h1><img src="画像%201.png?thumb#fig">'
                  '<img src="data:image/png;base64,AAAA"></body></html>')
        self.add(name, source)
        self.add('articles/智歯 1/画像 1.png', b'figure bytes')
        entries = build(self.root, self.out)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['id'], name)
        self.assertEqual(entries[0]['path'], 'articles/%E6%99%BA%E6%AD%AF%201/index.html')
        self.assertEqual(entries[0]['title'], '歯 & 顎')
        self.assertEqual(entries[0]['category'], '口腔外科')
        catalog = (self.out / 'assets/catalog-data.js').read_text()
        self.assertNotIn('</script>', catalog)
        self.assertEqual(json.loads(catalog.removeprefix('window.STUDY_CATALOG = ').strip()[:-1]), entries)
        served = (self.out / name).read_bytes().decode()
        self.assertIn('href="../../index.html#catalog"', served)
        self.assertIn('name="viewport" content="width=device-width', served)
        self.assertIn(':where(img,svg){max-width:100%}', served)
        original_markup = re.sub(r'<nav data-study-reader-nav\b[^>]*>.*?</nav>|<style data-study-fit>.*?</style>|<meta data-study-viewport[^>]*>', '', served, flags=re.S)
        self.assertEqual(original_markup, source)
        self.assertEqual((self.out / 'articles/智歯 1/画像 1.png').read_bytes(), b'figure bytes')
        self.add(name, '<h1>第2版</h1>')
        second = build(self.root, self.out.parent / 'next-release')
        self.assertEqual(second[0]['path'], entries[0]['path'])
        self.assertEqual(second[0]['id'], entries[0]['id'])
        self.assertEqual(second[0]['title'], '第2版')

    def test_renaming_and_restoring_a_title_keeps_the_article_and_its_url(self):
        name = 'articles/日本語 の原本.html'
        body = '<h1>誌面の見出し</h1><img src="data:image/png;base64,AAAA">'
        source = ('<!doctype html>\r\n<html><head><TiTle\n lang="en">Original &amp; Title</TiTle>'
                  '</head><body>' + body + '</body></html>')
        article = self.add(name, source)
        self.add(name + '.meta.json', json.dumps({'title': '  保存版 <図> & A  ', 'tags': ['T']}))
        edited = build(self.root, self.out / 'renamed')[0]
        self.assertEqual(edited['metadataFields'], ['title', 'tags'])
        self.assertEqual((edited['title'], edited['titleOverride'], edited['sourceTitle']),
                         ('保存版 <図> & A', '保存版 <図> & A', 'Original & Title'))
        served = (self.out / 'renamed' / name).read_bytes().decode()
        self.assertIn('<TiTle\n lang="en">保存版 &lt;図&gt; &amp; A</TiTle>', served)
        self.assertIn(body, served)
        self.assertIn('<h3>保存版 &lt;図&gt; &amp; A</h3>', (self.out / 'renamed/index.html').read_text())
        self.add(name + '.meta.json', '{"title":"","tags":["T"]}')
        restored = build(self.root, self.out / 'restored')[0]
        self.assertEqual((restored['id'], restored['path'], restored['tags']), (edited['id'], edited['path'], ['T']))
        self.assertEqual((restored['title'], restored['titleOverride']), ('Original & Title', ''))
        self.assertEqual(article.read_bytes(), source.encode())

    def test_article_without_a_document_title_gets_a_tab_title_and_keeps_figure_titles(self):
        name = 'articles/figure.htm'
        body = '<svg><title>図の説明</title></svg><h1>研究結果</h1>'
        self.add(name, body)
        self.add(name + '.meta.json', '{"title":"掲載名"}')
        entry = build(self.root, self.out)[0]
        self.assertEqual((entry['title'], entry['sourceTitle']), ('掲載名', '研究結果'))
        served = (self.out / name).read_text()
        self.assertIn('<title>掲載名</title>', served)
        self.assertIn(body, served)

    def test_invalid_article_title_stops_the_build(self):
        name = 'articles/article.html'
        self.add(name, '<h1>研究</h1>')
        for i, title in enumerate([None, 10, '本' * 301, 'ab\0cd']):
            with self.subTest(title_type=type(title)):
                self.add(name + '.meta.json', json.dumps({'title': title}))
                with self.assertRaisesRegex(ValueError, '文献タイトル'):
                    build(self.root, self.out / str(i))

    def test_authored_viewport_is_retained_and_absolute_project_image_resolves(self):
        supplied = '<meta name="viewport" content="width=device-width, initial-scale=0.9">'
        self.add('articles/paper.html', '<!DOCTYPE html><html><head>' + supplied + '</head>'
                 '<body><img src="/y-sensei-study-library/articles/fig.jpg"></body></html>')
        self.add('articles/fig.jpg', b'image')
        build(self.root, self.out)
        served = (self.out / 'articles/paper.html').read_text()
        self.assertIn(supplied, served)
        self.assertEqual(served.count('name="viewport"'), 1)

    def test_missing_local_figure_stops_publication(self):
        self.add('articles/paper.html', '<img src="Figures/missing.png">')
        with self.assertRaisesRegex(ValueError, 'Figures/missing.png'):
            build(self.root, self.out)

    def test_remote_base_keeps_home_on_github_pages(self):
        self.add('articles/paper.htm', '<base href="https://media.example.org/"><body><img src="figure.jpg">')
        build(self.root, self.out)
        self.assertIn('https://mxe050.github.io/y-sensei-study-library/#catalog', (self.out / 'articles/paper.htm').read_text())

    def test_edit_links_select_the_same_article_from_shelf_and_reader(self):
        shelf = 'https://mxe050.github.io/y-sensei-study-library/'
        name = 'articles/象牙 & +#?%2F/index.html'
        body = '<h1>解説</h1><p>本文</p>'
        for case, source, base in [
            ('fragment', body, urljoin(shelf, quote(name))),
            ('remote-base', '<html><head><base href="https://media.example.org/"></head>'
             '<body>' + body + '</body></html>', 'https://media.example.org/'),
        ]:
            with self.subTest(case=case):
                self.add(name, source)
                destination = self.out / case
                build(self.root, destination)
                index = (destination / 'index.html').read_text()
                reader = (destination / name).read_text()
                row = index.split('<li data-article-id=', 1)[1].split('</ul>', 1)[0]
                main_end = row.index('</a>')
                edit = re.search(r'<a\b(?=[^>]*\barticle-edit\b)[^>]*>(.*?)</a>', row, re.S)
                self.assertIsNotNone(edit)
                self.assertGreater(edit.start(), main_end)
                reader_edit = re.search(r'<a\b(?=[^>]*\bdata-study-edit\b)[^>]*>(.*?)</a>', reader, re.S)
                self.assertIsNotNone(reader_edit)
                self.assertLess(reader_edit.end(), reader.index(body))
                for link, document_base in [(edit, shelf), (reader_edit, base)]:
                    self.assertIn('分類・タグを編集', link[1])
                    href = unescape(re.search(r'href="([^"]+)"', link[0])[1])
                    target = urlsplit(urljoin(document_base, href))
                    self.assertEqual(target.scheme + '://' + target.netloc + target.path, shelf + 'manage.html')
                    self.assertEqual(parse_qs(target.query).get('article'), [name])


if __name__ == '__main__':
    unittest.main()
