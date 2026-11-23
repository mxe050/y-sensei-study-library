(() => {
  const settings = document.getElementById('site-title-settings');
  const form = document.getElementById('site-title-form');
  const input = document.getElementById('site-title');
  const save = document.getElementById('site-title-save');
  const requestBody = document.getElementById('site-title-request');
  const error = document.getElementById('site-title-error');
  const current = document.querySelector('.wordmark').textContent.trim();
  input.value = current;

  function update() {
    const title = input.value.trim().replace(/\s+/gu, ' ');
    const tooLong = [...title].length > 80;
    const invalid = /[\u0000-\u001f\u007f-\u009f\ud800-\udfff]/u.test(title);
    input.setCustomValidity(!title ? '書斎のタイトルを入力してください。' :
      tooLong ? '書斎のタイトルは80文字までです。' :
      invalid ? '制御文字を除いてください。' : '');
    error.textContent = input.validationMessage;
    save.disabled = title === current || !input.validity.valid;
    requestBody.value = save.disabled ? '' : JSON.stringify({siteTitle: title, previous: {siteTitle: current}});
  }

  function openLinkedSettings() {
    if (location.hash === '#site-title-settings') settings.open = true;
  }

  input.addEventListener('input', update);
  form.addEventListener('submit', (event) => {
    update();
    if (save.disabled) event.preventDefault();
  });
  window.addEventListener('hashchange', openLinkedSettings);
  openLinkedSettings();
  update();
})();
