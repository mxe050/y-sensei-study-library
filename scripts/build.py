"""Build the public reading shelf from files committed under articles/."""

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import re
from pathlib import Path
import shutil
import subprocess
from urllib.parse import quote, unquote, urljoin, urlsplit

from site_settings import DEFAULT_TITLE, read_site_title


ROOT = Path(__file__).resolve().parents[1]
SITE_FILES = ('index.html', 'manage.html', 'assets/style.css', 'assets/catalog.js',
              'assets/manage.css', 'assets/manage.js', 'assets/site-title.js')
DOCUMENT_EXTENSIONS = {'.html', '.htm'}
# Resolve URLs against a project subdirectory, as on GitHub project Pages.
PAGES_ORIGIN = 'https://mxe050.github.io'
PROJECT_BASE = '/y-sensei-study-library/'
PUBLICATION_ORIGIN = 'https://y-sensei-study-library.mxe05064.chatgpt.site'
MANAGEMENT_URL = 'https://private-study-library.mxe05064.chatgpt.site/public-manage'


def read_publication(root):
    """Opt in to the known migration without changing the preserved source files."""
    settings = root / 'publication.json'
    if not settings.is_file():
        return None
    config = json.loads(settings.read_text(encoding='utf-8'))
    expected = {'mode': 'redirect', 'publicOrigin': PUBLICATION_ORIGIN,
                'managementUrl': MANAGEMENT_URL}
    if config != expected:
        raise ValueError('publication.json: 移行先の固定設定を確認してください。')
    return config


def migration_page(target, title, *, management=False, articles=()):
    """Keep a usable link with JS disabled; never take a redirect URL from input."""
    config = json.dumps({'target': target, 'management': management,
                         'articles': list(articles)}, ensure_ascii=False)
    config = config.replace('<', r'\u003c').replace('\u2028', r'\u2028').replace('\u2029', r'\u2029')
    label = '掲載・編集画面を開く' if management else '文献の書斎を開く'
    explanation = ('掲載・編集は、いつもの本人専用書斎から行えます。' if management
                   else '文献の書斎を新しい公開先で開きます。')
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}｜移転のお知らせ</title>
<meta name="robots" content="noindex, follow"><link rel="canonical" href="{escape(target, quote=True)}">
<style>body{{margin:0;background:#f8fafb;color:#183139;font:16px/1.9 system-ui,-apple-system,"Yu Gothic",Meiryo,sans-serif}}main{{max-width:42rem;margin:12vh auto;padding:2rem;background:#fff;border:1px solid #dbe5e4;border-radius:.6rem}}h1{{font-size:1.5rem;line-height:1.6}}a{{color:#21675f;text-underline-offset:.2em;overflow-wrap:anywhere}}.open{{display:inline-block;padding:.65rem 1rem;border:1px solid #21675f;border-radius:.3rem;font-weight:700}}@media(max-width:600px){{main{{margin:2rem 1rem;padding:1.5rem}}}}</style>
</head><body><main><h1>{escape(title)}</h1><p>{explanation}</p><p>自動で移動しない場合は、次のリンクを開いてください。</p><p><a class="open" id="destination" href="{escape(target, quote=True)}">{label}</a></p></main>
<script>
(() => {{
  'use strict';
  const config = {config};
  const target = new URL(config.target);
  if (config.management) {{
    const article = new URLSearchParams(location.search).get('article');
    if (article && config.articles.includes(article)) target.searchParams.set('article', article);
  }} else {{
    target.search = location.search;
  }}
  target.hash = location.hash;
  document.getElementById('destination').href = target.href;
  location.replace(target.href);
}})();
</script></body></html>
'''


def write_publication_redirects(output, entries, site_title, config):
    origin = config['publicOrigin']
    index = migration_page(origin + '/', site_title)
    (output / 'index.html').write_text(index, encoding='utf-8')
    (output / 'manage.html').write_text(
        migration_page(config['managementUrl'], site_title + '｜掲載・編集', management=True,
                       articles=(entry['id'] for entry in entries)), encoding='utf-8')
    for entry in entries:
        target = origin + '/' + quote(entry['id'], safe='/')
        (output / entry['id']).write_text(migration_page(target, entry['title']), encoding='utf-8')
    # Previously cached catalog screens can detect the changed entry point.
    (output / 'catalog-version.json').write_text(
        json.dumps({'version': hashlib.sha256(index.encode('utf-8')).hexdigest()[:20]}), encoding='utf-8')


class ArticleParser(HTMLParser):
    """Read catalog metadata, image paths and native HTML insertion positions."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.parts = {'title': [], 'h1': []}
        self.capture = ''
        self.finished = set()
        self.text_exclusions = []
        self.title_start = self.title_end = None
        self.base = None
        self.images = []
        self.open_positions = {}
        self.doctype_end = None
        self.first_content = None
        self.head_containers = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if self.first_content is None:
            if tag in {'head', 'title', 'style', 'script', 'template', 'noscript'}:
                self.head_containers.append(tag)
            elif not self.head_containers and tag not in {'html', 'meta', 'base', 'link'}:
                self.first_content = self.getpos()
        if tag in {'head', 'html', 'body'} and tag not in self.open_positions:
            row, column = self.getpos()
            self.open_positions[tag] = (row, column + len(self.get_starttag_text()))
        if tag in {'svg', 'math', 'template', 'noscript'}:
            self.text_exclusions.append(tag)
        if tag in self.parts and tag not in self.finished and not self.text_exclusions:
            self.capture = tag
            if tag == 'title':
                row, column = self.getpos()
                self.title_start = (row, column + len(self.get_starttag_text()))
        elif tag == 'meta':
            name = (values.get('name') or values.get('property') or '').casefold()
            self.meta.setdefault(name, values.get('content') or '')
        elif tag == 'base' and self.base is None and values.get('href'):
            self.base = values['href']
        elif tag in {'img', 'image'}:
            src = values.get('src') or values.get('href') or values.get('xlink:href')
            if src and not src.lstrip().lower().startswith('data:'):
                self.images.append(src.strip())

    def handle_decl(self, decl):
        if decl.casefold().startswith('doctype') and self.doctype_end is None:
            row, column = self.getpos()
            self.doctype_end = (row, column + len(decl) + 3)

    def handle_data(self, data):
        if self.first_content is None and not self.head_containers and data.lstrip('\ufeff').strip():
            self.first_content = self.getpos()
        if self.capture and not self.text_exclusions:
            self.parts[self.capture].append(data)

    def handle_endtag(self, tag):
        if self.head_containers and tag == self.head_containers[-1]:
            self.head_containers.pop()
        if tag == self.capture and not self.text_exclusions:
            if tag == 'title':
                self.title_end = self.getpos()
            self.finished.add(tag)
            self.capture = ''
        if self.text_exclusions and self.text_exclusions[-1] == tag:
            self.text_exclusions.pop()


def display_text(value):
    return ' '.join(value.split())


def article_title_override(value):
    if not isinstance(value, str):
        raise ValueError('文献タイトルには文字列を指定してください。')
    title = display_text(value)
    if len(title) > 300 or re.search(r'[\x00-\x1f\x7f-\x9f\ud800-\udfff]', title):
        raise ValueError('文献タイトルは300文字以内の表示できる文字で入力してください。')
    return title


def classification(article, meta):
    metadata = {}
    category = meta.get('study-category', '')
    tags = re.split(r'[,，、;；\r\n]', meta.get('study-tags', meta.get('keywords', '')))
    sidecar = article.with_name(article.name + '.meta.json')
    has_metadata = sidecar.is_file()
    if has_metadata:
        try:
            metadata = json.loads(sidecar.read_text(encoding='utf-8-sig'))
        except (ValueError, UnicodeError) as error:
            raise ValueError(f'{sidecar.name}: 文献情報のJSONを読み込めません。{error}') from error
        if not isinstance(metadata, dict):
            raise ValueError(f'{sidecar.name}: 文献情報にはJSONオブジェクトを指定してください。')
        category = metadata.get('category', category)
        tags = metadata.get('tags', tags)
        if not isinstance(category, str) or not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError(f'{sidecar.name}: category は文字列、tags は文字列の配列で指定してください。')
    cleaned_tags = dict.fromkeys(display_text(tag) for tag in tags if tag.strip())
    return {'category': display_text(category) or '未分類', 'tags': list(cleaned_tags),
            'titleOverride': article_title_override(metadata.get('title', '')), 'hasMetadata': has_metadata,
            'metadataFields': [field for field in ('title', 'category', 'tags') if field in metadata]}


def is_entry(relative):
    return relative.suffix.lower() in DOCUMENT_EXTENSIONS and (
        len(relative.parts) == 1 or relative.stem.casefold() == 'index'
    )


def update_date(root, article):
    result = subprocess.run(
        ['git', 'log', '-1', '--format=%cs', '--', str(article.relative_to(root))],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return datetime.fromtimestamp(article.stat().st_mtime, timezone.utc).date().isoformat()


def validate_images(parser, relative, present):
    article_url = PAGES_ORIGIN + PROJECT_BASE + quote(relative.as_posix())
    base = urljoin(article_url, parser.base) if parser.base else article_url
    broken = set()
    for ref in parser.images:
        target = urlsplit(urljoin(base, ref))
        if target.scheme in {'http', 'https'} and target.netloc != urlsplit(PAGES_ORIGIN).netloc:
            continue
        if ref.startswith('#'):
            continue
        path = unquote(target.path)
        if target.scheme not in {'http', 'https'} or not path.startswith(PROJECT_BASE) or path[len(PROJECT_BASE):] not in present:
            broken.add(ref)
    if broken:
        names = ', '.join(sorted(broken)[:8])
        raise ValueError(f'{relative}: 画像の参照先を確認してください。{names}')


def edit_link(article_id):
    return 'manage.html?article=' + quote(article_id, safe='')


def reader_html(source, parser, relative, site_title, *, title_override=''):
    # A document with a <base> can redirect even root-relative links. Use the
    # canonical project URL in that case so the link really leads to the shelf.
    if parser.base:
        root = PAGES_ORIGIN + PROJECT_BASE
        home = root + '#catalog'
    else:
        root = '../' * (len(relative.parts) - 1)
        home = root + 'index.html#catalog'
    edit = root + edit_link(relative.as_posix())
    name = escape(site_title)
    nav = (f'<nav data-study-reader-nav aria-label="{name}" lang="ja">'
           f'<a data-study-home href="{home}" target="_self">← {name}へ</a>'
           f'<a data-study-edit href="{edit}" target="_self">タイトル・分類・タグを編集</a></nav>')
    added_head = ('<style data-study-fit>@media(max-width:760px){'
                  ':where(img,svg){max-width:100%}:where(img){height:auto}}'
                  'nav[data-study-reader-nav]{position:static;display:flex;flex-wrap:wrap;align-items:center;'
                  'gap:6px;padding:6px 10px;background:#faf8f2;color:#244d43}'
                  'nav[data-study-reader-nav] a{box-sizing:border-box;display:inline-flex;align-items:center;'
                  'min-height:44px;max-width:100%;overflow-wrap:anywhere;padding:6px 12px;background:#f2f4ed;color:#244d43;border:1px solid #9dad9f;'
                  'border-radius:4px;font:600 14px/1.5 system-ui;text-decoration:underline}'
                  '@media print{nav[data-study-reader-nav]{display:none}}</style>')
    if 'viewport' not in parser.meta:
        added_head = ('<meta data-study-viewport name="viewport" '
                      'content="width=device-width, initial-scale=1">') + added_head

    # Work against the original offsets to preserve all authored body markup and image bytes.
    line_offsets = [0] + [m.end() for m in re.finditer('\\n', source)]
    def offset(position, fallback):
        if position is None:
            return fallback
        row, column = position
        return line_offsets[row - 1] + column

    positions = parser.open_positions
    head_position = positions.get('head') or positions.get('html') or parser.doctype_end
    head_at = offset(head_position, int(source.startswith('\ufeff')))
    body_at = max(head_at, offset(positions.get('body') or parser.first_content, len(source)))
    edits = [(body_at, body_at, nav)]
    if title_override:
        title_text = escape(title_override, quote=False)
        if parser.title_end is None:
            added_head = '<title>' + title_text + '</title>' + added_head
        else:
            edits.append((offset(parser.title_start, head_at), offset(parser.title_end, head_at), title_text))
    edits.append((head_at, head_at, added_head))
    for start, end, text in sorted(edits, key=lambda edit: edit[0], reverse=True):
        source = source[:start] + text + source[end:]
    return source


def publish_article(root, article, present, destination, site_title):
    relative = article.relative_to(root)
    parser = ArticleParser()
    source = article.read_bytes().decode('utf-8')
    parser.feed(source)
    parser.close()
    validate_images(parser, relative, present)
    filename_title = article.parent.name if article.stem.lower() == 'index' else article.stem
    source_title = display_text(''.join(parser.parts['title'])) or display_text(''.join(parser.parts['h1'])) or filename_title
    metadata = classification(article, parser.meta)
    rendered = reader_html(source, parser, relative, site_title, title_override=metadata['titleOverride'])
    destination.write_bytes(rendered.encode('utf-8'))
    summary = display_text(parser.meta.get('description') or parser.meta.get('og:description', ''))
    return {
        'id': relative.as_posix(), 'path': quote(relative.as_posix()), 'title': metadata['titleOverride'] or source_title,
        'sourceTitle': source_title, **metadata,
        'summary': summary, 'updated': update_date(root, article),
    }


def article_row(entry):
    year, month, day = entry['updated'].split('-')
    date_text = f'{year}年{int(month)}月{int(day)}日 更新'
    summary = f'<p>{escape(entry["summary"])}</p>' if entry['summary'] else ''
    tags = ''
    if entry['tags']:
        labels = ''.join(f'<li>{escape(tag)}</li>' for tag in entry['tags'])
        tags = f'<ul class="article-tags" aria-label="タグ">{labels}</ul>'
    return (f'<li data-article-id="{escape(entry["id"])}"><a class="article-link" href="{escape(entry["path"])}">'
            f'<div class="article-meta"><span class="article-category">{escape(entry["category"])}</span>'
            f'<time datetime="{entry["updated"]}">{date_text}</time></div>'
            f'<h3>{escape(entry["title"])}</h3>{summary}{tags}</a>'
            f'<a class="article-edit" href="{edit_link(entry["id"])}" '
            f'aria-label="タイトル・分類・タグを編集（{escape(entry["title"])}）">タイトル・分類・タグを編集</a></li>')


def write_catalog(root, output, entries, site_title):
    data = json.dumps(entries, ensure_ascii=False, separators=(',', ':'))
    data = data.replace('<', r'\u003c').replace('\u2028', r'\u2028').replace('\u2029', r'\u2029')
    # Keep already-cached pages from the first edition working.
    (output / 'assets/catalog-data.js').write_text('window.STUDY_CATALOG = ' + data + ';\n', encoding='utf-8')
    marker = '<script type="application/json" id="catalog-data">[]</script>'
    name = escape(site_title)
    common = {marker: marker.replace('>[]<', '>' + data + '<'), '{{SITE_TITLE}}': name}
    cover_title = ('<span>Y先生</span><strong>文献の書斎</strong>' if site_title == DEFAULT_TITLE
                   else f'<strong>{name}</strong>')
    # Version the script and stylesheet URLs when their contents change.
    # Catalog records are embedded in the document itself.
    versions = {}
    for name in SITE_FILES:
        if name.startswith('assets/'):
            versions[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()[:12]
    asset_link = re.compile(r'((?:src|href)="(?:\./)?)(assets/[\w.-]+)(")')
    for page in ('index.html', 'manage.html'):
        template = (root / page).read_text(encoding='utf-8')
        template = asset_link.sub(lambda match: (match[1] + match[2] + '?v=' + versions[match[2]] + match[3])
                                  if match[2] in versions else match[0], template)
        replacements = common.copy()
        if page == 'index.html':
            replacements.update({
                '<!--site-cover-title-->': cover_title,
                '<!--catalog-count-->': f'{len(entries)}件',
                '<!--catalog-rows-->': '\n'.join(article_row(entry) for entry in entries),
                'data-empty-state hidden': 'data-empty-state hidden' if entries else 'data-empty-state',
            })
        for token in replacements:
            if token not in template or (token != '{{SITE_TITLE}}' and template.count(token) != 1):
                raise ValueError(f'{page}: 目録のテンプレートに必要な項目を確認してください。{token}')
        pattern = re.compile('|'.join(map(re.escape, replacements)))
        rendered = pattern.sub(lambda match: replacements[match[0]], template)
        if page == 'index.html':
            version_marker = '<!--catalog-version-->'
            if rendered.count(version_marker) != 1:
                raise ValueError(f'{page}: 目録の版を示す項目がありません。')
            version = hashlib.sha256(rendered.encode('utf-8')).hexdigest()[:20]
            rendered = rendered.replace(version_marker, version)
            (output / 'catalog-version.json').write_text(json.dumps({'version': version}), encoding='utf-8')
        (output / page).write_text(rendered, encoding='utf-8')


def build(root, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError(f'出力先には空のフォルダを指定してください。{output}')
    publication = read_publication(root)
    site_title = read_site_title(root)
    article_dir = root / 'articles'
    sources = []
    for path in sorted(article_dir.rglob('*')):
        relative = path.relative_to(article_dir)
        if any(part.startswith('.') for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f'リンクの代わりに実ファイルを配置してください。articles/{relative}')
        if path.is_file():
            sources.append(path)
    public_files = set(SITE_FILES) | {p.relative_to(root).as_posix() for p in sources}
    entries = []
    output.mkdir(parents=True, exist_ok=True)
    for path in [*(root / name for name in SITE_FILES), *sources]:
        dest = output / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.is_relative_to(article_dir) and is_entry(path.relative_to(article_dir)):
            entries.append(publish_article(root, path, public_files, dest, site_title))
        else:
            shutil.copyfile(path, dest)
    entries.sort(key=lambda entry: (entry['title'], entry['id']))
    entries.sort(key=lambda entry: entry['updated'], reverse=True)
    write_catalog(root, output, entries, site_title)
    (output / 'site-settings.json').write_text(
        json.dumps({'title': site_title}, ensure_ascii=False) + '\n', encoding='utf-8')
    if publication:
        write_publication_redirects(output, entries, site_title, publication)
    (output / '.nojekyll').touch()
    return entries


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, default=ROOT / '_site')
    arguments = cli.parse_args()
    try:
        result = build(ROOT, arguments.output)
    except (ValueError, OSError) as error:
        cli.exit(1, f'{error}\n')
    print(f'{len(result)} 編の公開用HTMLを {arguments.output} に生成しました。')
