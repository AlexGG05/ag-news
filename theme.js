(() => {
  const root = document.documentElement;
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = null;
  try { preference = localStorage.getItem('ag-news-theme'); } catch (_) {}
  if (!['light', 'dark'].includes(preference)) preference = null;
  const apply = () => {
    const dark = preference ? preference === 'dark' : system.matches;
    root.dataset.theme = dark ? 'dark' : 'light';
    const button = document.getElementById('theme-toggle');
    if (button) {
      const english = root.lang === 'en';
      button.textContent = dark ? (english ? '☀ Light' : '☀ Hell') : (english ? '☾ Dark' : '☾ Dunkel');
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', english ? (dark ? 'Enable light mode' : 'Enable dark mode') : (dark ? 'Hellen Modus aktivieren' : 'Dunklen Modus aktivieren'));
    }
  };
  apply();
  system.addEventListener('change', apply);
  window.addEventListener('storage', event => {
    if (event.key === 'ag-news-theme' || event.key === null) {
      preference = ['light', 'dark'].includes(event.newValue) ? event.newValue : null;
      apply();
    }
  });
  document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('theme-toggle');
    button.hidden = false;
    button.addEventListener('click', () => {
      preference = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('ag-news-theme', preference); } catch (_) {}
      apply();
    });
    apply();
  });
})();
