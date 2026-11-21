'use strict';

(() => {
  const tools = document.getElementById('search-tools');
  const query = document.getElementById('query');
  const category = document.getElementById('category');
  const list = document.getElementById('articles');
  const total = document.getElementById('total');
  const announcement = document.getElementById('announcement');
  const empty = document.getElementById('empty');
  const emptyTitle = document.getElementById('empty-title');
  const emptyText = document.getElementById('empty-text');
  const reset = document.getElementById('reset');

  function textElement(tag, text, className) {
    const element = document.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  function showEmpty(title, description, canReset = false) {
    emptyTitle.textContent = title;
    emptyText.textContent = description;
    reset.hidden = !canReset;
    empty.hidden = false;
  }

  if (!Array.isArray(window.STUDY_CATALOG)) {
    showEmpty('文献一覧を読み込めませんでした', '通信状況を確認して、このページを再度開いてください。');
    return;
  }

  function normalizeText(text) {
    return String(text || '').normalize('NFKC').toLocaleLowerCase('ja');
  }

  function prepareArticle(row) {
    if (!row || !row.title || typeof row.path !== 'string') return null;
    const base = new URL('./articles/', location.href);
    let url;
    try { url = new URL(row.path, location.href); } catch { return null; }
    if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname) || !/\.html?$/i.test(url.pathname)) return null;
    return {
      ...row,
      href: url.href,
      category: row.category || '',
      searchableText: normalizeText([row.title, row.category, row.summary].join(' ')),
    };
  }

  const records = window.STUDY_CATALOG.map(prepareArticle).filter(Boolean);
  records.sort((a, b) => String(b.updated || '').localeCompare(String(a.updated || '')) || a.title.localeCompare(b.title, 'ja'));
  const categories = [...new Set(records.map(article => article.category).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ja'));
  for (const name of categories) category.add(new Option(name, name));
  tools.hidden = records.length === 0;

  function articleRow(article) {
    const li = document.createElement('li');
    const link = document.createElement('a');
    link.className = 'article-link';
    link.href = article.href;
    const meta = document.createElement('div');
    meta.className = 'article-meta';
    if (article.category) meta.append(textElement('span', article.category, 'article-category'));
    if (article.updated && /^\d{4}-\d\d-\d\d$/.test(article.updated)) {
      const [year, month, day] = article.updated.split('-');
      const time = textElement('time', `${year}年${Number(month)}月${Number(day)}日 更新`);
      time.dateTime = article.updated;
      meta.append(time);
    }
    if (meta.childElementCount) link.append(meta);
    link.append(textElement('h3', article.title));
    if (article.summary) link.append(textElement('p', article.summary));
    li.append(link);
    return li;
  }

  function render() {
    const words = normalizeText(query.value).trim().split(/\s+/).filter(Boolean);
    const filtered = Boolean(words.length || category.value);
    const matches = records.filter(article => (!category.value || article.category === category.value) && words.every(word => article.searchableText.includes(word)));
    list.replaceChildren(...matches.map(articleRow));
    total.textContent = filtered ? `${records.length}件中 ${matches.length}件` : `${records.length}件`;
    announcement.textContent = `掲載文献 ${total.textContent}`;
    empty.hidden = true;
    if (!records.length) showEmpty('公開された文献はまだありません', '掲載された論文の批判的吟味は、ここからお読みいただけます。');
    else if (!matches.length) showEmpty('該当する文献がありません', 'キーワードや分野を変えてお試しください。', true);
  }

  function restoreFilters() {
    const params = new URLSearchParams(location.search);
    query.value = params.get('q') || '';
    category.value = categories.includes(params.get('category')) ? params.get('category') : '';
    render();
  }

  function updateFilters() {
    const url = new URL(location.href);
    for (const field of [query, category]) {
      if (field.value) url.searchParams.set(field.name, field.value);
      else url.searchParams.delete(field.name);
    }
    // The filtered list can be bookmarked and remains in the reader's back history.
    if (url.href !== location.href) {
      try { history.replaceState(history.state, '', url); } catch { /* Filtering also works in local previews. */ }
    }
    render();
  }

  tools.addEventListener('submit', event => {
    event.preventDefault();
    updateFilters();
  });
  query.addEventListener('input', updateFilters);
  category.addEventListener('change', updateFilters);
  reset.addEventListener('click', () => {
    query.value = '';
    category.value = '';
    updateFilters();
    query.focus();
  });
  window.addEventListener('popstate', restoreFilters);
  restoreFilters();
})();
