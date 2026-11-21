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


ROOT = Path(__file__).resolve().parents[1]
SITE_FILES = ('index.html', 'manage.html', 'assets/style.css', 'assets/catalog.js',
              'assets/manage.css', 'assets/manage.js')
DOCUMENT_EXTENSIONS = {'.html', '.htm'}
# Resolve URLs against a project subdirectory, as on GitHub project Pages.
PAGES_ORIGIN = 'https://mxe050.github.io'
PROJECT_BASE = '/y-sensei-study-library/'


class ArticleParser(HTMLParser):
    """Read catalog metadata, image paths and native HTML insertion positions."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.parts = {'title': [], 'h1': []}
        self.capture = ''
        self.finished = set()
        self.base = None
        self.images = []
        self.open_positions = {}
        self.doctype_end = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in {'head', 'html', 'body'} and tag not in self.open_positions:
            row, column = self.getpos()
            self.open_positions[tag] = (row, column + len(self.get_starttag_text()))
        if tag in self.parts and tag not in self.finished:
            self.capture = tag
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
        if self.capture:
            self.parts[self.capture].append(data)

    def handle_endtag(self, tag):
        if tag == self.capture:
            self.finished.add(tag)
            self.capture = ''


def display_text(value):
    return ' '.join(value.split())


def classification(article, meta):
    category = meta.get('study-category', '')
    tags = re.split(r'[,，、;；\r\n]', meta.get('study-tags', meta.get('keywords', '')))
    sidecar = article.with_name(article.name + '.meta.json')
    has_metadata = sidecar.is_file()
    if has_metadata:
        try:
            metadata = json.loads(sidecar.read_text(encoding='utf-8-sig'))
        except (ValueError, UnicodeError) as error:
            raise ValueError(f'{sidecar.name}: 分類・タグのJSONを読み込めません。{error}') from error
        if not isinstance(metadata, dict):
            raise ValueError(f'{sidecar.name}: 分類・タグにはJSONオブジェクトを指定してください。')
        category = metadata.get('category', category)
        tags = metadata.get('tags', tags)
        if not isinstance(category, str) or not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError(f'{sidecar.name}: category は文字列、tags は文字列の配列で指定してください。')
    cleaned_tags = dict.fromkeys(display_text(tag) for tag in tags if tag.strip())
    return {'category': display_text(category) or '未分類', 'tags': list(cleaned_tags), 'hasMetadata': has_metadata}


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


def reader_html(source, parser, relative):
    # A document with a <base> can redirect even root-relative links. Use the
    # canonical project URL in that case so the link really leads to the shelf.
    if parser.base:
        home = PAGES_ORIGIN + PROJECT_BASE + '#catalog'
    else:
        home = '../' * (len(relative.parts) - 1) + 'index.html#catalog'
    link = (f'<a data-study-home href="{home}" target="_self" lang="ja" '
            'style="display:inline-block;margin:6px 10px;padding:7px 12px;'
            'background:#f2f4ed;color:#244d43;border:1px solid #b5c8ba;'
            'border-radius:4px;font:500 14px/1.5 system-ui;text-decoration:underline;">'
            '← Y先生文献の書斎へ</a>')
    added_head = ('<style data-study-fit>@media(max-width:760px){'
                  ':where(img,svg){max-width:100%}:where(img){height:auto}}'
                  '</style>')
    if 'viewport' not in parser.meta:
        added_head = ('<meta data-study-viewport name="viewport" '
                      'content="width=device-width, initial-scale=1">') + added_head

    # Keep every original character, including CRLF and long embedded images.
    # Insert from the end so that one insertion cannot shift the other.
    line_offsets = [0] + [m.end() for m in re.finditer('\\n', source)]
    def offset(position, fallback):
        if position is None:
            return fallback
        row, column = position
        return line_offsets[row - 1] + column

    positions = parser.open_positions
    head_position = positions.get('head') or positions.get('html') or parser.doctype_end
    head_at = offset(head_position, int(source.startswith('\ufeff')))
    body_at = offset(positions.get('body'), len(source))
    for at, text in sorted([(head_at, added_head), (body_at, link)], key=lambda pair: pair[0], reverse=True):
        source = source[:at] + text + source[at:]
    return source


def publish_article(root, article, present, destination):
    relative = article.relative_to(root)
    parser = ArticleParser()
    source = article.read_bytes().decode('utf-8')
    parser.feed(source)
    parser.close()
    validate_images(parser, relative, present)
    destination.write_bytes(reader_html(source, parser, relative).encode('utf-8'))
    filename_title = article.parent.name if article.stem.lower() == 'index' else article.stem
    title = display_text(''.join(parser.parts['title'])) or display_text(''.join(parser.parts['h1'])) or filename_title
    summary = display_text(parser.meta.get('description') or parser.meta.get('og:description', ''))
    return {
        'id': relative.as_posix(), 'path': quote(relative.as_posix()), 'title': title,
        **classification(article, parser.meta),
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
            f'<h3>{escape(entry["title"])}</h3>{summary}{tags}</a></li>')


def write_catalog(root, output, entries):
    data = json.dumps(entries, ensure_ascii=False, separators=(',', ':'))
    data = data.replace('<', r'\u003c').replace('\u2028', r'\u2028').replace('\u2029', r'\u2029')
    # Keep already-cached pages from the first edition working.
    (output / 'assets/catalog-data.js').write_text('window.STUDY_CATALOG = ' + data + ';\n', encoding='utf-8')
    marker = '<script type="application/json" id="catalog-data">[]</script>'
    common = {marker: marker.replace('>[]<', '>' + data + '<')}
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
                '<!--catalog-count-->': f'{len(entries)}件',
                '<!--catalog-rows-->': '\n'.join(article_row(entry) for entry in entries),
                'data-empty-state hidden': 'data-empty-state hidden' if entries else 'data-empty-state',
            })
        for token in replacements:
            if template.count(token) != 1:
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
            entries.append(publish_article(root, path, public_files, dest))
        else:
            shutil.copyfile(path, dest)
    entries.sort(key=lambda entry: (entry['title'], entry['id']))
    entries.sort(key=lambda entry: entry['updated'], reverse=True)
    write_catalog(root, output, entries)
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
