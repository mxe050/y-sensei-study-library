(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const repo = 'https://github.com/mxe050/y-sensei-study-library';
  const target = byId('target');
  const input = byId('html-file');
  const panel = byId('inspection');
  const preview = byId('preview');
  const frame = byId('document');
  const category = byId('category');
  const tags = byId('tags');
  const download = byId('download-meta');
  const upload = byId('upload');
  const entries = new Map();
  const newMetadata = () => ({category: '', tags: []});
  let prepared = '';
  let readVersion = 0;
  let fileStatus = '';
  let fileReady = false;
  let fileMetadata = newMetadata();
  let touched = {category: false, tags: false};

  function articleParts(path) {
    if (typeof path !== 'string') return null;
    try {
      const parts = path.replace(/^\.\//, '').split('/').map(decodeURIComponent);
      if (parts[0] !== 'articles' || parts.length < 2 || !/\.html?$/i.test(parts.at(-1))) return null;
      if (parts.some(part => !part || part === '.' || part === '..' || /[\\/\u0000-\u001f]/.test(part))) return null;
      return parts;
    } catch {
      return null;
    }
  }

  const catalog = JSON.parse(byId('catalog-data').textContent);
  const categories = new Set();
  for (const item of catalog) {
    const parts = articleParts(item.path);
    if (!parts || entries.has(item.path)) continue;
    const metadata = {category: item.category === '未分類' ? '' : item.category || '', tags: item.tags || []};
    if (metadata.category) categories.add(metadata.category);
    entries.set(item.path, {parts, metadata, previous: {category: item.category || '未分類', tags: metadata.tags}, hasMetadata: item.hasMetadata});
    target.add(new Option(item.title || parts.at(-1), item.path));
  }
  for (const name of [...categories].sort((a, b) => a.localeCompare(b, 'ja'))) {
    byId('category-options').append(new Option(name, name));
  }

  function splitTags(text) {
    return [...new Set(text.split(/[,，、;；\r\n]+/).map(tag => tag.trim()).filter(Boolean))];
  }

  function formMetadata() {
    return {category: category.value.trim(), tags: splitTags(tags.value)};
  }

  function metadataFilename() {
    const entry = entries.get(target.value);
    return (entry ? entry.parts.at(-1) : input.files[0].name) + '.meta.json';
  }

  function showDestination() {
    const entry = entries.get(target.value);
    const parts = entry?.parts;
    const directory = parts ? parts.slice(0, -1) : ['articles'];
    const encodedDirectory = directory.map(encodeURIComponent).join('/');
    const file = input.files[0];
    byId('destination').textContent = entry ? `保存先　${parts.join('/')}` : '保存先　articles/';
    byId('file-label').textContent = entry ? '新しいHTMLに差し替える（任意）' : '公開するHTMLファイル';
    const mismatch = parts && file && parts.at(-1) !== file.name;
    const status = byId('selection');
    status.textContent = fileStatus || (entry ? '分類・タグだけを変えるときは、ファイルの選択は不要です。' : 'ファイルを選ぶと、本文と画像をこの端末で確認できます。');
    status.classList.toggle('warning', Boolean(mismatch));
    if (mismatch) status.textContent += ` 差し替えるには、ファイル名を「${parts.at(-1)}」に変更して選び直してください。`;

    // A replacement inherits a saved sidecar. Without one, compare to
    // metadata in the replacement HTML so a displayed classification is kept.
    const baseline = entry && (entry.hasMetadata || !file) ? entry.metadata : fileMetadata;
    const metadata = formMetadata();
    const changed = JSON.stringify(metadata) !== JSON.stringify(baseline);
    const metadataOnly = Boolean(entry && !file && changed);
    const basicUpload = !entry && !file && !changed;
    const instruction = byId('upload-instruction');
    const valid = [...metadata.category].length <= 100 && metadata.tags.length <= 20 && metadata.tags.every(tag => [...tag].length <= 60);
    const canSave = valid && !mismatch && (file ? fileReady : metadataOnly || basicUpload);
    let issueUrl;
    if (valid && metadataOnly) {
      const request = {article: parts.join('/'), previous: entry.previous, ...metadata};
      issueUrl = new URL(repo + '/issues/new');
      issueUrl.searchParams.set('title', '[書斎] 分類・タグを保存');
      issueUrl.searchParams.set('body', JSON.stringify(request, null, 2));
    }
    // Long Japanese URLs can exceed GitHub's request limit. The file upload
    // route saves the same data without putting it in a URL.
    const useIssue = Boolean(issueUrl && issueUrl.href.length < 7200);
    byId('issue-actions').hidden = !useIssue;
    byId('fallback').hidden = !useIssue;
    if (useIssue) byId('issue-save').href = issueUrl.href;
    const fileActions = byId('file-actions');
    const container = byId(useIssue ? 'fallback-body' : 'standard-actions');
    if (fileActions.parentElement !== container) {
      container.append(fileActions);
      byId('fallback').open = false;
    }
    fileActions.hidden = !canSave;
    download.hidden = !changed;
    upload.href = repo + '/upload/main/' + encodedDirectory;
    const fileInstruction = byId('file-instruction');
    instruction.textContent = '';
    fileInstruction.textContent = '';
    if (!valid) {
      instruction.textContent = '分類は100文字以内、タグは1件60文字以内で20件まで入力できます。';
      return;
    }
    if (!canSave) {
      instruction.textContent = file ? status.textContent : entry ? '分類・タグを編集するか、差し替えるHTMLを選んでください。' : '公開するHTMLを選んでください。分類とタグは任意です。';
      return;
    }
    const bundleNote = ' 別添え画像は、HTMLとのフォルダ構成を保って一緒に追加してください。';
    if (changed) {
      const name = metadataFilename();
      const files = file ? `「${file.name}」と「${name}」` : `「${name}」`;
      if (useIssue) instruction.textContent = 'この文献の分類・タグを更新します。本文と公開URLはそのままです。';
      fileInstruction.textContent = `分類ファイルをダウンロードし、GitHubのアップロード画面で${files}を選んでください。` + (file ? bundleNote : '');
    } else if (file) {
      fileInstruction.textContent = `GitHubのアップロード画面で「${file.name}」を選びます。` + bundleNote;
    } else {
      fileInstruction.textContent = '公開するHTMLをGitHubにアップロードしてください。分類やタグを一緒に登録するときは、先にこの画面でHTMLを選んで入力します。';
    }
  }
  target.addEventListener('change', () => {
    const metadata = entries.get(target.value)?.metadata || newMetadata();
    category.value = metadata.category;
    tags.value = metadata.tags.join('、');
    touched = {category: false, tags: false};
    input.value = '';
    resetFile();
    showDestination();
  });
  for (const field of [category, tags]) {
    field.addEventListener('input', () => {
      touched[field.id] = true;
      byId('save-status').textContent = '';
      showDestination();
    });
  }
  download.addEventListener('click', () => {
    const name = metadataFilename();
    const blob = new Blob([JSON.stringify(formMetadata(), null, 2) + '\n'], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 30000);
    byId('save-status').textContent = `続いて「${name}」をGitHubにアップロードしてください。ダウンロード時にファイル名に (1) などが付いた場合は元の名前に戻してください。`;
  });
  byId('latest').addEventListener('click', event => {
    event.currentTarget.href = './index.html?refresh=' + Date.now() + '#catalog';
  });

  byId('latest-manage').addEventListener('click', event => {
    const url = new URL('./manage.html', location.href);
    const selected = entries.get(target.value);
    if (selected) url.searchParams.set('article', selected.parts.join('/'));
    url.searchParams.set('refresh', Date.now());
    event.currentTarget.href = url.href;
  });

  function resetFile() {
    readVersion++;
    prepared = '';
    frame.removeAttribute('srcdoc');
    preview.open = false;
    panel.hidden = true;
    fileStatus = '';
    fileReady = false;
    fileMetadata = newMetadata();
    byId('save-status').textContent = '';
  }

  const requestedArticle = new URL(location.href).searchParams.get('article');
  for (const [path, entry] of entries) {
    if (requestedArticle === entry.parts.join('/')) {
      target.value = path;
      target.dispatchEvent(new Event('change'));
      break;
    }
  }
  showDestination();

  function inspectImages(fragment) {
    const local = new Set();
    let embedded = 0;
    let remote = 0;
    const record = raw => {
      const value = (raw || '').trim();
      if (!value || value.startsWith('#')) return;
      if (/^data:image\//i.test(value)) embedded++;
      else if (/^(?:https?:)?\/\//i.test(value)) remote++;
      else local.add(value);
    };
    fragment.querySelectorAll('img,image,picture source').forEach(node => {
      record(node.getAttribute('src') || node.getAttribute('href') || node.getAttribute('xlink:href'));
      const srcset = node.getAttribute('srcset') || '';
      // URLs in srcset are whitespace delimited and can include data URI commas.
      for (const match of srcset.matchAll(/(?:^|,\s*)((?:data:[^\s]+|[^,\s]+))(?:\s+[^,]*)?/gi)) record(match[1].replace(/,$/, ''));
    });
    const container = byId('images');
    const counts = document.createElement('p');
    counts.textContent = `画像参照　埋め込み ${embedded}件・外部URL ${remote}件・別ファイル ${local.size}件`;
    container.replaceChildren(counts);
    if (local.size) {
      const details = document.createElement('details');
      const label = document.createElement('summary');
      label.textContent = `一緒に用意する画像ファイル（${local.size}件）`;
      const list = document.createElement('ul');
      for (const path of local) {
        const li = document.createElement('li');
        li.textContent = path;
        list.append(li);
      }
      details.append(label, list);
      container.append(details);
    }
  }
  function preparePreview(html) {
    // Template contents are inert, including <img> with external src URLs.
    const template = document.createElement('template');
    template.innerHTML = html;
    const fragment = template.content;
    inspectImages(fragment);
    const meta = new Map();
    for (const node of fragment.querySelectorAll('meta')) {
      const key = (node.getAttribute('name') || node.getAttribute('property') || '').toLowerCase();
      if (!meta.has(key)) meta.set(key, node.getAttribute('content') || '');
    }
    fileMetadata = {
      category: (meta.get('study-category') || '').trim(),
      tags: splitTags(meta.get('study-tags') || meta.get('keywords') || '')
    };
    if (!entries.has(target.value)) {
      if (!touched.category) category.value = fileMetadata.category;
      if (!touched.tags) tags.value = fileMetadata.tags.join('、');
    }
    const name = (fragment.querySelector('title')?.textContent || fragment.querySelector('h1')?.textContent || '').trim();
    fragment.querySelectorAll('script,meta,link,base,iframe,frame,object,embed,form,template,noscript,foreignObject,animate,animateTransform,set').forEach(node => node.remove());
    for (const node of fragment.querySelectorAll('*')) {
      for (const {name: attr, value} of [...node.attributes]) {
        if (/^on|^(srcdoc|srcset|target|action|formaction|ping|poster|autofocus)$/i.test(attr)) node.removeAttribute(attr);
        if (/^(src|href|xlink:href)$/i.test(attr)) {
          const image = ['img','image'].includes(node.localName) && /^data:image\//i.test(value);
          if (!image && !value.startsWith('#')) node.removeAttribute(attr);
        }
      }
    }
    const policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'";
    prepared = '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'+policy+'"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>'+template.innerHTML+'</body></html>';
    return name;
  }
  preview.addEventListener('toggle', () => {
    if (preview.open && prepared && !frame.hasAttribute('srcdoc')) frame.srcdoc = prepared;
  });
  input.addEventListener('change', async () => {
    resetFile();
    const version = readVersion;
    const file = input.files[0];
    fileStatus = file ? 'HTMLを読み込み中です。' : '';
    showDestination();
    if (!file) return;
    if (!/\.html?$/i.test(file.name)) {
      fileStatus = '拡張子が .html または .htm のファイルを選んでください。';
      showDestination();
      return;
    }
    try {
      const html = await file.text();
      if (version !== readVersion) return;
      if (!html.trim()) throw new Error();
      const name = preparePreview(html);
      fileStatus = `選択中　${name || file.name}`;
      fileReady = true;
      panel.hidden = false;
    } catch {
      if (version !== readVersion) return;
      fileStatus = 'HTMLを読み込めませんでした。ファイルの内容を確認して選び直してください。';
    }
    showDestination();
  });
})();
