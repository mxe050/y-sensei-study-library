"""Persist a shelf rename after the common workflow verifies its author."""

import json

from site_settings import normalize_site_title, read_site_title


class SiteTitleError(ValueError):
    pass


def save_site_title(root, data):
    if (not isinstance(data, dict) or set(data) != {'siteTitle', 'previous'}
            or not isinstance(data['previous'], dict) or set(data['previous']) != {'siteTitle'}):
        raise SiteTitleError('書斎のタイトルを変更する画面を開き直してください。')
    path = root / 'site-settings.json'
    if path.is_symlink():
        raise SiteTitleError('書斎の設定ファイルを確認してください。')
    try:
        title = normalize_site_title(data['siteTitle'])
        previous = normalize_site_title(data['previous']['siteTitle'])
        current = read_site_title(root)
    except ValueError as error:
        raise SiteTitleError('書斎のタイトルは1〜80文字で指定してください。現在の書斎設定も確認してください。') from error
    if current == title:
        return None
    if current != previous:
        raise SiteTitleError('編集中に書斎のタイトルが変わりました。最新の掲載・編集画面から変更してください。')
    path.write_text(json.dumps({'title': title}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path.name
