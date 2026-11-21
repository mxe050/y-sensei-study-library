(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const uploadRoot = 'https://github.com/mxe050/y-sensei-study-library/upload/main/';
  const target = byId('target');
  const input = byId('html-file');
  const panel = byId('inspection');
  const preview = byId('preview');
  const frame = byId('document');
  const entries = new Map();
  let prepared = '';
  let readVersion = 0;
  let fileStatus = '';

  // The catalog contains relative URLs. Validate every decoded path component
  // before using it to construct a GitHub destination.
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
  for (const item of Array.isArray(window.STUDY_CATALOG) ? window.STUDY_CATALOG : []) {
    const parts = articleParts(item.path);
    if (!parts || entries.has(item.path)) continue;
    entries.set(item.path, parts);
    target.add(new Option(String(item.title || parts.at(-1)), item.path));
  }
  function showDestination() {
    const parts = entries.get(target.value);
    const directory = parts ? parts.slice(0, -1) : ['articles'];
    byId('destination').textContent = parts ? `差し替え先　${parts.join('/')}` : '保存先　articles/';
    byId('upload').href = uploadRoot + directory.map(encodeURIComponent).join('/');
    const filename = input.files[0]?.name;
    const mismatch = parts && filename && parts.at(-1) !== filename;
    const status = byId('selection');
    status.textContent = fileStatus || '選択したファイルは、この端末でプレビューできます。';
    status.classList.toggle('warning', Boolean(mismatch));
    if (mismatch) status.textContent += ` 差し替えるには、アップロード前にファイル名を「${parts.at(-1)}」に変更してください。`;
    byId('upload-instruction').textContent = parts
      ? `次の画面で「${parts.at(-1)}」を選び直し、同じ場所に保存します。文献の公開URLが引き継がれます。別ファイルの画像も更新する場合は、元のフォルダ構成で追加してください。`
      : '次の画面で公開するHTMLをもう一度選びます。別ファイルの画像は、HTMLから参照しているフォルダ構成のまま一緒に追加してください。';
  }
  target.addEventListener('change', showDestination);
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
    const version = ++readVersion;
    prepared = '';
    frame.removeAttribute('srcdoc');
    preview.open = false;
    panel.hidden = true;
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
      panel.hidden = false;
    } catch {
      if (version !== readVersion) return;
      fileStatus = 'HTMLを読み込めませんでした。ファイルの内容を確認して選び直してください。';
    }
    showDestination();
  });
})();
