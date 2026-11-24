/**
 * NexChecker — API Docs Interactive Engine & Live Playground
 */
(function () {
  'use strict';

  const tg = window.Telegram?.WebApp;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.BackButton) {
        tg.BackButton.show();
        tg.BackButton.onClick(() => { window.location.href = '/'; });
      }
    } catch (_) {}
  }

  const ORIGIN = window.location.origin;

  const BRAND_LOGOS = {
    zomato: '/static/src/logos/zomato.png',
    flipkart: '/static/src/logos/flipkart.png',
    meesho: '/static/src/logos/meesho.png',
    myntra: '/static/src/logos/myntra.png',
    swiggy: '/static/src/logos/swiggy.png',
    amazon: '/static/src/logos/amazon.png',
  };

  // ── Presets for Interactive Playground ──────────────────────────────────────
  const PRESETS = {
    health: {
      method: 'GET',
      path: '/api/health',
      needsBody: false,
      authHints: [],
      body: null,
    },
    platforms: {
      method: 'GET',
      path: '/api/platforms',
      needsBody: false,
      authHints: [],
      body: null,
    },
    purchase: {
      method: 'POST',
      path: '/api/v1/purchase',
      needsBody: true,
      authHints: ['apiKey', 'nexnumKey'],
      body: {
        platform: 'zomato',
        target_status: 'NOT_REGISTERED',
        service_code: 'dy',
        country_code: '22',
        max_attempts: 5,
      },
    },
    check_phone: {
      method: 'POST',
      path: '/api/checker/phone',
      needsBody: true,
      authHints: ['tgInit'],
      body: {
        phone: '9876543210',
        platform: 'zomato',
      },
    },
    check_batch: {
      method: 'POST',
      path: '/api/checker/batch',
      needsBody: true,
      authHints: ['tgInit'],
      body: {
        phones: ['9876543210', '9876543211'],
        platform: 'flipkart',
      },
    },
    auth_verify: {
      method: 'GET',
      path: '/api/auth/verify',
      needsBody: false,
      authHints: ['tgInit'],
      body: null,
    },
    auth_me: {
      method: 'GET',
      path: '/api/auth/me',
      needsBody: false,
      authHints: ['tgInit'],
      body: null,
    },
    history_get: {
      method: 'GET',
      path: '/api/history?limit=20',
      needsBody: false,
      authHints: ['tgInit'],
      body: null,
    },
    history_clear: {
      method: 'POST',
      path: '/api/history/clear',
      needsBody: false,
      authHints: ['tgInit'],
      body: null,
    },
    admin_users: {
      method: 'GET',
      path: '/api/admin/users',
      needsBody: false,
      authHints: [],
      body: null,
    },
  };

  // ── DOM References ──────────────────────────────────────────────────────────
  const el = {
    sidebar: document.getElementById('docsSidebar'),
    backdrop: document.getElementById('sidebarBackdrop'),
    menuToggle: document.getElementById('menuToggle'),
    sidebarSearch: document.getElementById('sidebarSearch'),
    navLinks: document.querySelectorAll('#sidebarNav .nav-link'),
    navGroups: document.querySelectorAll('#sidebarNav .nav-group'),

    baseUrlText: document.getElementById('baseUrlText'),
    copyBaseUrlBtn: document.getElementById('copyBaseUrlBtn'),
    liveHealthPill: document.getElementById('liveHealthPill'),
    liveHealthText: document.getElementById('liveHealthText'),
    statTotalChecks: document.getElementById('statTotalChecks'),
    statBreakdown: document.getElementById('statBreakdown'),

    brandThemeSelect: document.getElementById('brandThemeSelect'),
    headerBrandLogo: document.getElementById('headerBrandLogo'),
    toast: document.getElementById('docsToast'),

    pgEndpointSelect: document.getElementById('pgEndpointSelect'),
    pgSendBtn: document.getElementById('pgSendBtn'),
    pgResetBtn: document.getElementById('pgResetBtn'),
    pgApiKey: document.getElementById('pgApiKey'),
    pgNexNumKey: document.getElementById('pgNexNumKey'),
    pgTgInitData: document.getElementById('pgTgInitData'),
    pgFieldApiKey: document.getElementById('pgFieldApiKey'),
    pgFieldNexNumKey: document.getElementById('pgFieldNexNumKey'),
    pgFieldTgInit: document.getElementById('pgFieldTgInit'),
    pgBodyWrap: document.getElementById('pgBodyWrap'),
    pgBodyInput: document.getElementById('pgBodyInput'),
    pgOutput: document.getElementById('pgOutput'),
    pgStatusChip: document.getElementById('pgStatusChip'),
    pgLatencyLabel: document.getElementById('pgLatencyLabel'),
    pgSnippetPre: document.getElementById('pgSnippetPre'),
    pgCopySnippetBtn: document.getElementById('pgCopySnippetBtn'),
    snippetTabs: document.querySelectorAll('.code-tab'),
  };

  let activeSnippetLang = 'curl';

  // ── Toast & Clipboard ───────────────────────────────────────────────────────
  function showToast(msg) {
    if (!el.toast) return;
    el.toast.textContent = msg;
    el.toast.classList.add('show');
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => el.toast.classList.remove('show'), 1800);
  }

  function copyText(text, label = 'Copied to clipboard!') {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => showToast(label)).catch(() => fallbackCopy(text, label));
    } else {
      fallbackCopy(text, label);
    }
  }

  function fallbackCopy(text, label) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(label);
  }

  // ── Base URL ────────────────────────────────────────────────────────────────
  if (el.baseUrlText) el.baseUrlText.textContent = ORIGIN;
  if (el.copyBaseUrlBtn) {
    el.copyBaseUrlBtn.addEventListener('click', () => copyText(ORIGIN, 'Base URL copied!'));
  }

  // ── Brand Theme Switcher ────────────────────────────────────────────────────
  function applyBrandTheme(brand) {
    const safeBrand = BRAND_LOGOS[brand] ? brand : 'zomato';
    document.documentElement.setAttribute('data-brand', safeBrand);
    if (el.headerBrandLogo) el.headerBrandLogo.src = BRAND_LOGOS[safeBrand];
    if (el.brandThemeSelect) el.brandThemeSelect.value = safeBrand;
    localStorage.setItem('nex_docs_brand', safeBrand);
  }

  if (el.brandThemeSelect) {
    el.brandThemeSelect.addEventListener('change', (e) => applyBrandTheme(e.target.value));
  }
  applyBrandTheme(localStorage.getItem('nex_docs_brand') || 'zomato');

  // ── Sidebar Mobile Drawer & Search ──────────────────────────────────────────
  function toggleSidebar(forceOpen) {
    const open = typeof forceOpen === 'boolean' ? forceOpen : !el.sidebar.classList.contains('open');
    el.sidebar.classList.toggle('open', open);
    el.backdrop.classList.toggle('open', open);
  }

  if (el.menuToggle) el.menuToggle.addEventListener('click', () => toggleSidebar());
  if (el.backdrop) el.backdrop.addEventListener('click', () => toggleSidebar(false));

  el.navLinks.forEach((link) => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 960) toggleSidebar(false);
    });
  });

  // Search filter
  if (el.sidebarSearch) {
    el.sidebarSearch.addEventListener('input', (e) => {
      const q = e.target.value.trim().toLowerCase();
      el.navGroups.forEach((grp) => {
        let visibleCount = 0;
        grp.querySelectorAll('.nav-link').forEach((lnk) => {
          const match = !q || lnk.textContent.toLowerCase().includes(q) || (lnk.getAttribute('href') || '').toLowerCase().includes(q);
          lnk.style.display = match ? 'flex' : 'none';
          if (match) visibleCount++;
        });
        grp.style.display = visibleCount > 0 ? 'block' : 'none';
      });
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
        e.preventDefault();
        el.sidebarSearch.focus();
      }
    });
  }

  // Scroll spy
  const sections = document.querySelectorAll('section.doc-section, h3[id], div[id^="ep-"]');
  function updateActiveNav() {
    let currentId = 'overview';
    const scrollPos = window.scrollY + 110;
    sections.forEach((sec) => {
      if (sec.offsetTop <= scrollPos && sec.id) {
        currentId = sec.id;
      }
    });
    el.navLinks.forEach((lnk) => {
      lnk.classList.toggle('active', lnk.getAttribute('href') === '#' + currentId);
    });
  }
  window.addEventListener('scroll', updateActiveNav, { passive: true });

  // ── Code Block Copy Buttons ─────────────────────────────────────────────────
  document.querySelectorAll('.copy-code-btn[data-copy-target]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.copyTarget);
      if (target) copyText(target.textContent, 'Copied!');
    });
  });

  // ── Live Health Poller ──────────────────────────────────────────────────────
  async function refreshHealth() {
    try {
      const res = await fetch('/api/health');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      if (el.liveHealthPill) el.liveHealthPill.className = 'health-pill online';
      if (el.liveHealthText) el.liveHealthText.textContent = 'LIVE v' + (data.version || '3.0.0');
      if (el.statTotalChecks) el.statTotalChecks.textContent = Number(data.total_checks || 0).toLocaleString();
      if (el.statBreakdown) {
        el.statBreakdown.textContent = `${data.registered_checks || 0} registered • ${data.fresh_checks || 0} fresh`;
      }
    } catch {
      if (el.liveHealthPill) el.liveHealthPill.className = 'health-pill offline';
      if (el.liveHealthText) el.liveHealthText.textContent = 'OFFLINE';
    }
  }
  refreshHealth();

  // ── Playground State & Persistence ──────────────────────────────────────────
  function restoreCredentials() {
    const savedApiKey = sessionStorage.getItem('nex_pg_api_key') || '';
    const savedNexKey = sessionStorage.getItem('nex_pg_nexnum_key') || '';
    const tgInit = window.Telegram?.WebApp?.initData || sessionStorage.getItem('nex_pg_tg_init') || '';
    if (el.pgApiKey) el.pgApiKey.value = savedApiKey;
    if (el.pgNexNumKey) el.pgNexNumKey.value = savedNexKey;
    if (el.pgTgInitData) el.pgTgInitData.value = tgInit;
  }

  function saveCredentials() {
    if (el.pgApiKey) sessionStorage.setItem('nex_pg_api_key', el.pgApiKey.value.trim());
    if (el.pgNexNumKey) sessionStorage.setItem('nex_pg_nexnum_key', el.pgNexNumKey.value.trim());
    if (el.pgTgInitData) sessionStorage.setItem('nex_pg_tg_init', el.pgTgInitData.value.trim());
  }

  function buildHeadersObj(preset) {
    const headers = {};
    if (preset.needsBody) headers['Content-Type'] = 'application/json';
    const apiKey = el.pgApiKey?.value.trim();
    const nexKey = el.pgNexNumKey?.value.trim();
    const tgInit = el.pgTgInitData?.value.trim();

    if (apiKey && preset.authHints.includes('apiKey')) headers['X-API-Key'] = apiKey;
    if (nexKey && preset.authHints.includes('nexnumKey')) headers['X-NexNum-Key'] = nexKey;
    if (tgInit && preset.authHints.includes('tgInit')) headers['X-Telegram-Init-Data'] = tgInit;
    return headers;
  }

  function renderCodeSnippet() {
    const key = el.pgEndpointSelect?.value || 'health';
    const preset = PRESETS[key];
    if (!preset || !el.pgSnippetPre) return;

    const url = ORIGIN + preset.path;
    const headers = buildHeadersObj(preset);
    const bodyText = preset.needsBody ? (el.pgBodyInput?.value.trim() || '{}') : '';

    if (activeSnippetLang === 'curl') {
      const lines = [`curl -X ${preset.method} "${url}"`];
      Object.entries(headers).forEach(([k, v]) => {
        lines.push(`  -H "${k}: ${v}"`);
      });
      if (preset.needsBody) {
        lines.push(`  -d '${bodyText.replace(/\n\s*/g, ' ')}'`);
      }
      el.pgSnippetPre.textContent = lines.join(' \\\n');
    } else if (activeSnippetLang === 'python') {
      const hdrStr = JSON.stringify(headers, null, 2);
      if (preset.needsBody) {
        el.pgSnippetPre.textContent =
`import requests

resp = requests.request(
    "${preset.method}",
    "${url}",
    headers=${hdrStr},
    json=${bodyText},
    timeout=60,
)
print(resp.status_code, resp.json())`;
      } else {
        el.pgSnippetPre.textContent =
`import requests

resp = requests.request(
    "${preset.method}",
    "${url}",
    headers=${hdrStr},
    timeout=30,
)
print(resp.status_code, resp.json())`;
      }
    } else {
      const opts = { method: preset.method, headers };
      let optsCode = JSON.stringify(opts, null, 2);
      if (preset.needsBody) {
        optsCode = optsCode.slice(0, -1) + `,\n  body: JSON.stringify(${bodyText})\n}`;
      }
      el.pgSnippetPre.textContent =
`const resp = await fetch("${url}", ${optsCode});
const data = await resp.json();
console.log(resp.status, data);`;
    }
  }

  function applyPreset(key) {
    const preset = PRESETS[key] || PRESETS.health;
    if (el.pgEndpointSelect) el.pgEndpointSelect.value = key;
    if (el.pgBodyWrap) el.pgBodyWrap.style.display = preset.needsBody ? 'flex' : 'none';
    if (el.pgBodyInput) {
      el.pgBodyInput.value = preset.needsBody && preset.body ? JSON.stringify(preset.body, null, 2) : '';
    }

    if (el.pgFieldApiKey) el.pgFieldApiKey.style.display = preset.authHints.includes('apiKey') ? 'flex' : 'none';
    if (el.pgFieldNexNumKey) el.pgFieldNexNumKey.style.display = preset.authHints.includes('nexnumKey') ? 'flex' : 'none';
    if (el.pgFieldTgInit) el.pgFieldTgInit.style.display = preset.authHints.includes('tgInit') ? 'flex' : 'none';

    renderCodeSnippet();
  }

  window.loadPlayground = function (presetKey) {
    applyPreset(presetKey);
    const pgSec = document.getElementById('playground');
    if (pgSec) pgSec.scrollIntoView({ behavior: 'smooth' });
  };

  if (el.pgEndpointSelect) {
    el.pgEndpointSelect.addEventListener('change', (e) => applyPreset(e.target.value));
  }
  if (el.pgResetBtn) {
    el.pgResetBtn.addEventListener('click', () => applyPreset(el.pgEndpointSelect.value));
  }

  [el.pgApiKey, el.pgNexNumKey, el.pgTgInitData, el.pgBodyInput].forEach((input) => {
    if (!input) return;
    input.addEventListener('input', () => {
      saveCredentials();
      renderCodeSnippet();
    });
  });

  el.snippetTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      el.snippetTabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      activeSnippetLang = tab.dataset.lang;
      renderCodeSnippet();
    });
  });

  if (el.pgCopySnippetBtn) {
    el.pgCopySnippetBtn.addEventListener('click', () => {
      if (el.pgSnippetPre) copyText(el.pgSnippetPre.textContent, 'Snippet copied!');
    });
  }

  // ── Execute Live HTTP Request ───────────────────────────────────────────────
  if (el.pgSendBtn) {
    el.pgSendBtn.addEventListener('click', async () => {
      const key = el.pgEndpointSelect.value;
      const preset = PRESETS[key];
      if (!preset) return;

      const headers = buildHeadersObj(preset);
      const fetchOpts = { method: preset.method, headers };

      if (preset.needsBody) {
        const rawBody = el.pgBodyInput.value.trim();
        try {
          JSON.parse(rawBody || '{}');
          fetchOpts.body = rawBody || '{}';
        } catch (err) {
          el.pgStatusChip.style.display = 'inline-block';
          el.pgStatusChip.className = 'status-chip s4xx';
          el.pgStatusChip.textContent = 'INVALID JSON';
          el.pgOutput.textContent = 'Body parse error: ' + err.message;
          return;
        }
      }

      el.pgSendBtn.disabled = true;
      el.pgSendBtn.textContent = 'Running...';
      const t0 = performance.now();

      try {
        const resp = await fetch(preset.path, fetchOpts);
        const elapsed = Math.round(performance.now() - t0);
        const text = await resp.text();
        let formatted = text;
        try {
          formatted = JSON.stringify(JSON.parse(text), null, 2);
        } catch (_) {}

        el.pgStatusChip.style.display = 'inline-block';
        el.pgStatusChip.className = 'status-chip ' + (resp.status < 300 ? 's2xx' : resp.status < 500 ? 's4xx' : 's5xx');
        el.pgStatusChip.textContent = `${resp.status} ${resp.statusText || ''}`.trim();
        el.pgLatencyLabel.textContent = `${elapsed} ms`;
        el.pgOutput.textContent = formatted;
      } catch (err) {
        el.pgStatusChip.style.display = 'inline-block';
        el.pgStatusChip.className = 'status-chip s5xx';
        el.pgStatusChip.textContent = 'NETWORK ERROR';
        el.pgLatencyLabel.textContent = '';
        el.pgOutput.textContent = String(err);
      } finally {
        el.pgSendBtn.disabled = false;
        el.pgSendBtn.textContent = '▶ Send Request';
      }
    });
  }

  // Initialize Playground
  restoreCredentials();
  applyPreset('purchase');
})();
