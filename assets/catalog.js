'use strict';

(() => {
  const byId = id => document.getElementById(id);
  const tools = byId('search-tools');
  const query = byId('query');
  const category = byId('category');
  const tag = byId('tag');
  const total = byId('total');
  const empty = byId('empty');
  const reset = byId('reset');
  const refresh = byId('refresh-catalog');

  function latestUrl() {
    const url = new URL(location.href);
    url.searchParams.set('latest', String(Date.now()));
    url.hash = 'catalog';
    return url.href;
  }
  // A browser can receive the new script while still displaying a first-edition shell.
  if (!refresh) {
    const link = document.createElement('a');
    link.textContent = '最新版の文献一覧を開く';
    link.href = latestUrl();
    total.after(link);
    if (!new URL(location.href).searchParams.has('latest')) location.replace(link.href);
    return;
  }
  function refreshLink() {
    refresh.href = latestUrl();
  }
  refreshLink();
  refresh.addEventListener('click', refreshLink);

  // Check the edition on return, including an empty shelf left open during upload.
  const edition = document.querySelector('meta[name="catalog-version"]')?.content;
  if (/^[0-9a-f]+$/.test(edition || '') && /^https?:$/.test(location.protocol)) {
    let lastCheck = 0;
    let pending = false;
    let found = false;
    async function checkEdition() {
      const now = Date.now();
      if (document.hidden || pending || found || now - lastCheck < 3000) return;
      pending = true;
      lastCheck = now;
      try {
        const response = await fetch(`./catalog-version.json?v=${now}`, {cache: 'no-store'});
        if (!response.ok) return;
        const latest = (await response.json()).version;
        if (typeof latest === 'string' && /^[0-9a-f]+$/.test(latest) && latest !== edition) {
          found = true;
          refresh.textContent = '新しい文献一覧を表示';
          refresh.classList.add('update-available');
          byId('catalog-freshness').textContent = '新しい文献一覧が公開されました。';
        }
      } catch {
        // A saved page or a temporary offline connection can still use its complete catalog.
      } finally {
        pending = false;
      }
    }
    window.addEventListener('pageshow', checkEdition);
    document.addEventListener('visibilitychange', checkEdition);
    // A publication may finish while the reader is already back on this tab.
    window.setInterval(checkEdition, 60000);
  }

  // Keep the published HTML readable even if interactive filtering cannot start.
  let catalog;
  try {
    catalog = JSON.parse(byId('catalog-data').textContent);
  } catch {
    return;
  }
  const rows = [...byId('articles').children];
  if (!Array.isArray(catalog) || !catalog.length || rows.length !== catalog.length) return;

  function normalize(text) {
    return String(text || '').normalize('NFKC').toLocaleLowerCase('ja');
  }

  const entries = new Map(catalog.map(article => [article.id, article]));
  const records = [];
  for (const row of rows) {
    const article = entries.get(row.dataset.articleId);
    if (!article || !Array.isArray(article.tags)) return;
    records.push({
      row, category: article.category, tags: article.tags,
      text: normalize([article.title, article.summary, article.category, ...article.tags].join(' ')),
    });
  }

  function addOptions(field, values) {
    const sorted = [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ja'));
    for (const value of sorted) field.add(new Option(value, value));
  }
  addOptions(category, records.map(record => record.category));
  addOptions(tag, records.flatMap(record => record.tags));
  tools.hidden = false;

  function filterList() {
    const words = normalize(query.value).trim().split(/\s+/).filter(Boolean);
    let count = 0;
    for (const record of records) {
      const matches = (!category.value || record.category === category.value)
        && (!tag.value || record.tags.includes(tag.value))
        && words.every(word => record.text.includes(word));
      record.row.hidden = !matches;
      if (matches) count++;
    }
    const active = Boolean(category.value || tag.value || words.length);
    total.textContent = active ? `${records.length}件中 ${count}件` : `${records.length}件`;
    byId('announcement').textContent = `掲載文献 ${total.textContent}`;
    empty.hidden = count > 0;
    if (!count) {
      byId('empty-title').textContent = '該当する文献がありません';
      byId('empty-text').textContent = 'キーワード、分類、タグを変えてお試しください。';
      reset.hidden = false;
    }
  }

  function restoreFilters() {
    const params = new URLSearchParams(location.search);
    query.value = params.get('q') || '';
    for (const field of [category, tag]) {
      const requested = params.get(field.name);
      field.value = [...field.options].some(option => option.value === requested) ? requested : '';
    }
    filterList();
    refreshLink();
  }

  function updateFilters() {
    const url = new URL(location.href);
    for (const field of [query, category, tag]) {
      if (field.value) url.searchParams.set(field.name, field.value);
      else url.searchParams.delete(field.name);
    }
    if (url.href !== location.href) {
      try { history.replaceState(history.state, '', url); } catch { /* Local file previews may restrict history. */ }
    }
    filterList();
    refreshLink();
  }
  tools.addEventListener('submit', event => {
    event.preventDefault();
    updateFilters();
  });
  query.addEventListener('input', updateFilters);
  category.addEventListener('change', updateFilters);
  tag.addEventListener('change', updateFilters);
  reset.addEventListener('click', () => {
    tools.reset();
    updateFilters();
    query.focus();
  });
  window.addEventListener('popstate', restoreFilters);
  restoreFilters();
})();
