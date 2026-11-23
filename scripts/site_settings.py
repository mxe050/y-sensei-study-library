"""Public site title shared by the Pages build and its owner editor."""

import json


DEFAULT_TITLE = 'Y先生文献の書斎'


def normalize_site_title(text):
    if not isinstance(text, str):
        raise ValueError('書斎のタイトルは文字列で入力してください。')
    title = ' '.join(text.split())
    if not 1 <= len(title) <= 80:
        raise ValueError('書斎のタイトルは1〜80文字で入力してください。')
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 or 0xd800 <= ord(char) <= 0xdfff for char in title):
        raise ValueError('書斎のタイトルに使用できない文字があります。')
    return title


def read_site_title(root):
    path = root / 'site-settings.json'
    if not path.exists():
        return DEFAULT_TITLE
    try:
        settings = json.loads(path.read_text(encoding='utf-8-sig'))
        return normalize_site_title(settings['title'])
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f'{path.name}: 書斎のタイトル設定を確認してください。{error}') from error
