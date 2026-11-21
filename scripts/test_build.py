import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

from build import build, SITE_FILES


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.out = Path(self.temp.name) / 'published'
        (self.root / 'articles').mkdir(parents=True)
        for name in SITE_FILES:
            self.add(name, b'')

    def add(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return path

    def test_empty_shelf_omits_unpublished_files(self):
        self.add('notes.json', 'private-only fixture')
        self.add('articles/.gitkeep', b'')
        self.assertEqual(build(self.root, self.out), [])
        self.assertFalse((self.out / 'notes.json').exists())
        self.assertFalse((self.out / 'articles/.gitkeep').exists())

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
        original_markup = re.sub(r'<a data-study-home[^>]+>.*?</a>|<style data-study-fit>.*?</style>|<meta data-study-viewport[^>]*>', '', served)
        self.assertEqual(original_markup, source)
        self.assertEqual((self.out / 'articles/智歯 1/画像 1.png').read_bytes(), b'figure bytes')
        self.add(name, '<h1>第2版</h1>')
        second = build(self.root, self.out.parent / 'next-release')
        self.assertEqual(second[0]['path'], entries[0]['path'])
        self.assertEqual(second[0]['id'], entries[0]['id'])
        self.assertEqual(second[0]['title'], '第2版')

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


if __name__ == '__main__':
    unittest.main()
