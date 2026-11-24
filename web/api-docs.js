/**
 * NexChecker — Dynamic API Docs & Interactive Playground
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

  // Dynamic platform state populated from GET /api/platforms
  let platformsList = [];
  let activePlatforms = [];
  let selectedPlatformKey = '';

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
      buildBody: (p) => ({
        platform: p ? p.key : 'zomato',
        target_status: 'NOT_REGISTERED',
        service_code: p ? p.service_code : 'dy',
        country_code: '22',
        max_attempts: 5,
      }),
    },
    check_phone: {
      method: 'POST',
      path: '/api/checker/phone',
      needsBody: true,
      authHints: ['tgInit'],
      buildBody: (p) => ({
        phone: '9876543210',
        platform: p ? p.key : 'zomato',
      }),
    },
    check_batch: {
      method: 'POST',
      path: '/api/checker/batch',
      needsBody: true,
      authHints: ['tgInit'],
      buildBody: (p) => ({
        phones: ['9876543210', '9876543211'],
        platform: p ? p.key : 'flipkart',
      }),
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
    sidebarActiveCount: document.getElementById('sidebarActiveCount'),
    navLinks: document.querySelectorAll('#sidebarNav .nav-link'),

    baseUrlText: document.getElementById('baseUrlText'),
    copyBaseUrlBtn: document.getElementById('copyBaseUrlBtn'),
    liveHealthPill: document.getElementById('liveHealthPill'),
    liveHealthText: document.getElementById('liveHealthText'),
    toast: document.getElementById('docsToast'),

    pgEndpointSelect: document.getElementById('pgEndpointSelect'),
    pgServicesBar: document.getElementById('pgServicesBar'),
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

    enginesTableBody: document.getElementById('enginesTableBody'),
    docDefaultPlatform: document.getElementById('docDefaultPlatform'),
    docPlatformListDesc: document.getElementById('docPlatformListDesc'),
    docServiceMapDesc: document.getElementById('docServiceMapDesc'),
    codePurchaseOk: document.getElementById('codePurchaseOk'),
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

  function copyText(text, label = 'Copied!') {
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

  // ── Sidebar Drawer & Scroll Spy ─────────────────────────────────────────────
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

  const sections = document.querySelectorAll('section.doc-section, h3[id]');
  function updateActiveNav() {
    let currentId = 'auth';
    const scrollPos = window.scrollY + 110;
    sections.forEach((sec) => {
      if (sec.offsetTop <= scrollPos && sec.id) currentId = sec.id;
    });
    el.navLinks.forEach((lnk) => {
      lnk.classList.toggle('active', lnk.getAttribute('href') === '#' + currentId);
    });
  }
  window.addEventListener('scroll', updateActiveNav, { passive: true });

  // ── Static Copy Buttons ─────────────────────────────────────────────────────
  document.querySelectorAll('.copy-code-btn[data-copy-target]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.copyTarget);
      if (target) copyText(target.textContent, 'Copied!');
    });
  });

  // ── Dynamic Platform Hydration from /api/platforms ──────────────────────────
  function getActivePlatformObj() {
    return (
      activePlatforms.find((p) => p.key === selectedPlatformKey) ||
      activePlatforms[0] ||
      platformsList[0] ||
      { key: 'zomato', label: 'Zomato', service_code: 'dy' }
    );
  }

  function renderActiveServicePills() {
    if (!el.pgServicesBar) return;
    if (!activePlatforms.length) {
      el.pgServicesBar.innerHTML = '<span class="pg-services-label">Active Services:</span><span style="font-size:12px;color:var(--text-muted);">None available</span>';
      return;
    }

    const pillsHtml = activePlatforms
      .map((p) => {
        const isSelected = p.key === selectedPlatformKey;
        const logoHtml = p.logo ? `<img src="${escapeHtml(p.logo)}" alt="${escapeHtml(p.label)}">` : '';
        return `
          <button type="button" class="pg-service-pill ${isSelected ? 'active' : ''}" data-platform-key="${escapeHtml(p.key)}">
            ${logoHtml}
            <span>${escapeHtml(p.label)}</span>
            <span class="svc-code">${escapeHtml(p.service_code || '')}</span>
          </button>`;
      })
      .join('');

    el.pgServicesBar.innerHTML = `<span class="pg-services-label">Active Services:</span>${pillsHtml}`;

    el.pgServicesBar.querySelectorAll('.pg-service-pill').forEach((btn) => {
      btn.addEventListener('click', () => {
        selectPlatform(btn.dataset.platformKey);
      });
    });
  }

  function selectPlatform(platformKey) {
    selectedPlatformKey = platformKey;
    renderActiveServicePills();
    updateDynamicPurchaseExample();

    const presetKey = el.pgEndpointSelect?.value || 'purchase';
    if (PRESETS[presetKey]?.buildBody) {
      applyPreset(presetKey);
    }
  }

  function updateDynamicPurchaseExample() {
    const active = getActivePlatformObj();
    if (el.docDefaultPlatform && active) {
      el.docDefaultPlatform.textContent = `"${active.key}"`;
    }
    if (el.docPlatformListDesc && activePlatforms.length) {
      const activeCodes = activePlatforms.map((p) => `<code>${escapeHtml(p.key)}</code>`).join(', ');
      const disabledList = platformsList.filter((p) => p.status !== 'active').map((p) => `<code>${escapeHtml(p.key)}</code>`).join(', ');
      el.docPlatformListDesc.innerHTML =
        `Active checker slug: ${activeCodes}.` +
        (disabledList ? ` (Currently disabled: ${disabledList}).` : '');
    }
    if (el.docServiceMapDesc && platformsList.length) {
      const mapStr = platformsList
        .map((p) => `${escapeHtml(p.key)}=<code>${escapeHtml(p.service_code || '—')}</code>`)
        .join(', ');
      el.docServiceMapDesc.innerHTML = `NexNum service code override (live defaults: ${mapStr}).`;
    }
    if (el.codePurchaseOk && active) {
      const sampleJson = {
        success: true,
        order_id: '1791225496122425077082',
        phone_number: '919876543210',
        clean_mobile: '9876543210',
        platform: active.key,
        status: 'NOT_REGISTERED',
        cost: 9.0,
        attempts_taken: 2,
        discarded_orders: [
          {
            order_id: '1791225496122425077081',
            phone_number: '919876543211',
            status: 'REGISTERED',
            cancellation: 'QUEUED_DEFERRED',
          },
        ],
        nexnum_direct_usage: {
          get_status_url: 'https://nexnum.in/stubs/handler_api.php?action=getStatus&id=1791225496122425077082&api_key=YOUR_NEXNUM_KEY',
          cancel_url: 'https://nexnum.in/stubs/handler_api.php?action=setStatus&id=1791225496122425077082&status=8&api_key=YOUR_NEXNUM_KEY',
        },
      };
      el.codePurchaseOk.textContent = JSON.stringify(sampleJson, null, 2);
    }
  }

  function renderEnginesTable() {
    if (!el.enginesTableBody) return;
    if (!platformsList.length) {
      el.enginesTableBody.innerHTML = '<tr><td colspan="5">No platforms returned by /api/platforms.</td></tr>';
      return;
    }

    el.enginesTableBody.innerHTML = platformsList
      .map((p) => {
        const isActive = p.status === 'active';
        const statusBadge = isActive
          ? '<span class="auth-badge active">ACTIVE</span>'
          : '<span class="auth-badge disabled">DISABLED</span>';
        const logoImg = p.logo ? `<img src="${escapeHtml(p.logo)}" alt="${escapeHtml(p.label)}">` : '';
        const actionBtn = isActive
          ? `<button type="button" class="try-btn" data-try-platform="${escapeHtml(p.key)}">Test ↗</button>`
          : '<span style="color:var(--text-muted);font-size:11px;">Unavailable</span>';

        return `
          <tr>
            <td><div class="engine-name-cell">${logoImg}<span>${escapeHtml(p.label)}</span></div></td>
            <td>${statusBadge}</td>
            <td><code>${escapeHtml(p.service_code || '—')}</code></td>
            <td><code>${escapeHtml(p.module || '')}</code> — ${escapeHtml(p.mechanism || '')}</td>
            <td>${actionBtn}</td>
          </tr>`;
      })
      .join('');

    el.enginesTableBody.querySelectorAll('[data-try-platform]').forEach((btn) => {
      btn.addEventListener('click', () => {
        selectPlatform(btn.dataset.tryPlatform);
        window.loadPlayground('purchase');
      });
    });
  }

  async function hydrateDynamicData() {
    // 1) Fetch /api/platforms
    try {
      const res = await fetch('/api/platforms');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      platformsList = Array.isArray(data.platforms) ? data.platforms : [];
      activePlatforms = platformsList.filter((p) => p.status === 'active');

      if (!selectedPlatformKey && activePlatforms.length) {
        selectedPlatformKey = activePlatforms[0].key;
      }

      if (el.sidebarActiveCount) {
        el.sidebarActiveCount.textContent = `${activePlatforms.length} / ${platformsList.length}`;
      }

      renderActiveServicePills();
      renderEnginesTable();
      updateDynamicPurchaseExample();
      applyPreset(el.pgEndpointSelect?.value || 'purchase');
    } catch (err) {
      if (el.enginesTableBody) {
        el.enginesTableBody.innerHTML = `<tr><td colspan="5" style="color:var(--red);">Failed to load /api/platforms: ${escapeHtml(err.message)}</td></tr>`;
      }
    }

    // 2) Fetch /api/health
    try {
      const res = await fetch('/api/health');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      if (el.liveHealthPill) el.liveHealthPill.className = 'health-pill online';
      if (el.liveHealthText) el.liveHealthText.textContent = 'LIVE v' + (data.version || '3.0.0');
    } catch {
      if (el.liveHealthPill) el.liveHealthPill.className = 'health-pill offline';
      if (el.liveHealthText) el.liveHealthText.textContent = 'OFFLINE';
    }
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Playground Controls ─────────────────────────────────────────────────────
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
    const key = el.pgEndpointSelect?.value || 'purchase';
    const preset = PRESETS[key];
    if (!preset || !el.pgSnippetPre) return;

    const url = ORIGIN + preset.path;
    const headers = buildHeadersObj(preset);
    const bodyText = preset.needsBody ? (el.pgBodyInput?.value.trim() || '{}') : '';

    if (activeSnippetLang === 'curl') {
      const lines = [`curl -X ${preset.method} "${url}"`];
      Object.entries(headers).forEach(([k, v]) => lines.push(`  -H "${k}: ${v}"`));
      if (preset.needsBody) lines.push(`  -d '${bodyText.replace(/\n\s*/g, ' ')}'`);
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
    const preset = PRESETS[key] || PRESETS.purchase;
    if (el.pgEndpointSelect) el.pgEndpointSelect.value = key;
    if (el.pgBodyWrap) el.pgBodyWrap.style.display = preset.needsBody ? 'flex' : 'none';

    const showServicesBar = Boolean(preset.buildBody);
    if (el.pgServicesBar) el.pgServicesBar.style.display = showServicesBar ? 'flex' : 'none';

    if (el.pgBodyInput) {
      const payload = preset.buildBody ? preset.buildBody(getActivePlatformObj()) : preset.body;
      el.pgBodyInput.value = preset.needsBody && payload ? JSON.stringify(payload, null, 2) : '';
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

  if (el.pgEndpointSelect) el.pgEndpointSelect.addEventListener('change', (e) => applyPreset(e.target.value));
  if (el.pgResetBtn) el.pgResetBtn.addEventListener('click', () => applyPreset(el.pgEndpointSelect.value));

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
        try { formatted = JSON.stringify(JSON.parse(text), null, 2); } catch (_) {}

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

  // Boot
  restoreCredentials();
  applyPreset('purchase');
  hydrateDynamicData();
})();
