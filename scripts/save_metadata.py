"""Apply an owner-submitted classification request against the current main branch."""

import json
import os
from pathlib import Path
import subprocess

from build import ArticleParser, ROOT, classification, display_text, is_entry


REPOSITORY = 'mxe050/y-sensei-study-library'
OWNER = REPOSITORY.split('/')[0]
ISSUE_TITLE = '[書斎] 分類・タグを保存'


class RequestError(ValueError):
    pass


def request_details(event):
    issue = event.get('issue', {})
    if (event.get('action') not in {'opened', 'reopened'}
            or event.get('repository', {}).get('full_name') != REPOSITORY
            or event.get('sender', {}).get('login') != OWNER
            or issue.get('user', {}).get('login') != OWNER
            or issue.get('title') != ISSUE_TITLE):
        raise RequestError('掲載者からの分類・タグ保存依頼を確認できません。')
    body = issue.get('body')
    if not isinstance(body, str) or len(body) > 24000:
        raise RequestError('保存フォームの内容を確認してください。')
    try:
        data = json.loads(body)
    except (ValueError, RecursionError) as error:
        raise RequestError('保存フォームの内容を読み取れません。') from error
    if not isinstance(data, dict) or set(data) != {'article', 'category', 'tags', 'previous'}:
        raise RequestError('保存フォームを開き直してください。')
    return data


def clean_labels(data, enforce_limits):
    if (not isinstance(data, dict) or not isinstance(data.get('category'), str)
            or not isinstance(data.get('tags'), list)
            or any(not isinstance(tag, str) for tag in data['tags'])):
        raise RequestError('分類とタグの入力形式を確認してください。')
    category = display_text(data['category'])
    tags = list(dict.fromkeys(display_text(tag) for tag in data['tags'] if tag.strip()))
    if enforce_limits and (len(category) > 100 or len(tags) > 20 or any(len(tag) > 60 for tag in tags)):
        raise RequestError('分類は100文字、タグは各60文字・20件までです。')
    return {'category': category, 'tags': tags}


def save(root, data):
    article_id = data['article']
    if not isinstance(article_id, str) or any(ord(char) < 32 for char in article_id):
        raise RequestError('文献の保存場所を確認してください。')
    parts = article_id.split('/')
    if (len(parts) < 2 or parts[0] != 'articles' or any(not part or part.startswith('.') for part in parts)
            or '\\' in article_id or not is_entry(Path(*parts[1:]))):
        raise RequestError('目録にある文献を選んでください。')
    article = root.joinpath(*parts)
    sidecar = article.with_name(article.name + '.meta.json')
    if not article.is_file() or article.resolve() != article or sidecar.is_symlink():
        raise RequestError('選択した文献が見つかりません。最新の掲載者メニューを開いてください。')
    parser = ArticleParser()
    parser.feed(article.read_text(encoding='utf-8-sig'))
    parser.close()
    stored = classification(article, parser.meta)
    current = {'category': stored['category'], 'tags': stored['tags']}
    previous = clean_labels(data['previous'], False)
    updated = clean_labels(data, True)
    visible = {**updated, 'category': updated['category'] or '未分類'}
    if current == visible:
        return None
    if previous != current:
        raise RequestError('編集中に分類・タグが変更されました。最新の掲載者メニューで確認して依頼し直してください。')
    sidecar.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return str(sidecar.relative_to(root))


def apply_on_main(root, data):
    def git(*args, **kwargs):
        return subprocess.run(['git', *args], cwd=root, **kwargs)

    git('config', 'user.name', 'github-actions[bot]', check=True)
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com', check=True)
    for _ in range(3):
        # This is a disposable Actions checkout. An intervening remote update
        # requires validating the same request against the new state again.
        git('fetch', '--no-tags', 'origin', 'refs/heads/main', check=True)
        git('reset', '--hard', 'FETCH_HEAD', check=True)
        path = save(root, data)
        if path is None:
            return
        git('--literal-pathspecs', 'add', '--', path, check=True)
        git('commit', '-m', '文献の分類とタグを更新', check=True)
        if git('push', 'origin', 'HEAD:refs/heads/main').returncode == 0:
            return
    raise RequestError('GitHubへの書き込みを完了できませんでした。公開処理の記録を確認してください。')


if __name__ == '__main__':
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    try:
        apply_on_main(ROOT, request_details(event))
    except RequestError as error:
        # RequestError messages are fixed strings and never include issue body values.
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f'reason={error}\n')
        raise SystemExit(str(error))
