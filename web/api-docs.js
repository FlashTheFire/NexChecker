/**
 * NexChecker — Dynamic API Reference Engine
 * Auto-cycling multi-service brand identity + live /api/platforms hydration
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

  const BRAND_ACCENTS = {
    zomato:   { accent: '#E23744', soft: 'rgba(226,55,68,0.13)',  glow: 'rgba(226,55,68,0.28)' },
    flipkart: { accent: '#3b82f6', soft: 'rgba(59,130,246,0.13)', glow: 'rgba(59,130,246,0.28)' },
    meesho:   { accent: '#a855f7', soft: 'rgba(168,85,247,0.13)', glow: 'rgba(168,85,247,0.28)' },
    myntra:   { accent: '#f43f5e', soft: 'rgba(244,63,94,0.13)',  glow: 'rgba(244,63,94,0.28)' },
    amazon:   { accent: '#f59e0b', soft: 'rgba(245,158,11,0.13)', glow: 'rgba(245,158,11,0.28)' },
    swiggy:   { accent: '#fb923c', soft: 'rgba(251,146,60,0.13)', glow: 'rgba(251,146,60,0.28)' },
    bigbasket:{ accent: '#84cc16', soft: 'rgba(132,204,22,0.13)', glow: 'rgba(132,204,22,0.28)' },
    zepto:    { accent: '#c084fc', soft: 'rgba(192,132,252,0.13)',glow: 'rgba(192,132,252,0.28)' },
  };

  let platformsList = [];
  let activePlatforms = [];
  let selectedPlatformKey = '';
  let cycleIdx = 0;
  let cycleTimer = null;
  let activeLang = 'curl';

  const el = {
    sidebar: document.getElementById('docsSidebar'),
    backdrop: document.getElementById('sidebarBackdrop'),
    menuToggle: document.getElementById('menuToggle'),
    navLinks: document.querySelectorAll('#sidebarNav .nav-link'),

    dynamicLogoFrame: document.getElementById('dynamicLogoFrame'),
    dynamicLogoImg: document.getElementById('dynamicLogoImg'),
    dynamicLogoFallback: document.getElementById('dynamicLogoFallback'),
    cyclingServiceLabel: document.getElementById('cyclingServiceLabel'),
    heroServiceStack: document.getElementById('heroServiceStack'),

    baseUrlText: document.getElementById('baseUrlText'),
    copyBaseUrlBtn: document.getElementById('copyBaseUrlBtn'),
    liveHealthPill: document.getElementById('liveHealthPill'),
    liveHealthText: document.getElementById('liveHealthText'),
    toast: document.getElementById('docsToast'),

    codePurchaseReq: document.getElementById('codePurchaseReq'),
    copyReqBtn: document.getElementById('copyReqBtn'),
    codeTabs: document.querySelectorAll('.code-tab'),

    docDefaultPlatform: document.getElementById('docDefaultPlatform'),
    docPlatformListDesc: document.getElementById('docPlatformListDesc'),
    docServiceMapDesc: document.getElementById('docServiceMapDesc'),
    codePurchaseOk: document.getElementById('codePurchaseOk'),
    enginesTableBody: document.getElementById('enginesTableBody'),
  };

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function showToast(msg) {
    if (!el.toast) return;
    el.toast.textContent = msg;
    el.toast.classList.add('show');
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => el.toast.classList.remove('show'), 1800);
  }

  function copyText(text, label = 'Copied!') {
    if (navigator.clipboard?.writeText) {
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

  if (el.baseUrlText) el.baseUrlText.textContent = ORIGIN;
  el.copyBaseUrlBtn?.addEventListener('click', () => copyText(ORIGIN, 'Base URL copied!'));

  // ── Sidebar Drawer & Scroll Spy ─────────────────────────────────────────────
  function toggleSidebar(forceOpen) {
    const open = typeof forceOpen === 'boolean' ? forceOpen : !el.sidebar.classList.contains('open');
    el.sidebar?.classList.toggle('open', open);
    el.backdrop?.classList.toggle('open', open);
  }

  el.menuToggle?.addEventListener('click', () => toggleSidebar());
  el.backdrop?.addEventListener('click', () => toggleSidebar(false));
  el.navLinks.forEach((link) => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 960) toggleSidebar(false);
    });
  });

  const sections = document.querySelectorAll('section.doc-section, h3[id]');
  window.addEventListener('scroll', () => {
    let currentId = 'auth';
    const scrollPos = window.scrollY + 115;
    sections.forEach((sec) => {
      if (sec.offsetTop <= scrollPos && sec.id) currentId = sec.id;
    });
    el.navLinks.forEach((lnk) => {
      lnk.classList.toggle('active', lnk.getAttribute('href') === '#' + currentId);
    });
  }, { passive: true });

  document.querySelectorAll('.copy-code-btn[data-copy-target]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.copyTarget);
      if (target) copyText(target.textContent, 'Copied!');
    });
  });

  // ── Dynamic Accent & Auto-Cycling Multi-Service Main Logo ───────────────────
  function applyBrandAccent(key) {
    const palette = BRAND_ACCENTS[key] || BRAND_ACCENTS.flipkart;
    const root = document.documentElement.style;
    root.setProperty('--accent', palette.accent);
    root.setProperty('--accent-soft', palette.soft);
    root.setProperty('--accent-glow', palette.glow);
  }

  function showLogoForPlatform(p, animate = true) {
    if (!p || !el.dynamicLogoImg || !el.cyclingServiceLabel) return;

    const applyUpdate = () => {
      if (p.logo) {
        el.dynamicLogoImg.src = p.logo;
        el.dynamicLogoImg.alt = p.label;
        el.dynamicLogoImg.classList.remove('is-hidden');
        if (el.dynamicLogoFallback) el.dynamicLogoFallback.style.display = 'none';
      } else {
        el.dynamicLogoImg.classList.add('is-hidden');
        if (el.dynamicLogoFallback) el.dynamicLogoFallback.style.display = 'block';
      }
      el.cyclingServiceLabel.textContent = `${p.label} • ${p.service_code || p.key}`;
      applyBrandAccent(p.key);
      el.dynamicLogoImg.classList.remove('is-switching');
      el.cyclingServiceLabel.classList.remove('is-switching');
    };

    if (!animate) {
      applyUpdate();
      return;
    }

    el.dynamicLogoImg.classList.add('is-switching');
    el.cyclingServiceLabel.classList.add('is-switching');
    setTimeout(applyUpdate, 160);
  }

  function startLogoCycler() {
    if (cycleTimer) clearInterval(cycleTimer);
    if (!activePlatforms.length) return;

    // Preload active service icons so transitions never flicker
    activePlatforms.forEach((p) => {
      if (p.logo) { const img = new Image(); img.src = p.logo; }
    });

    showLogoForPlatform(activePlatforms[0], false);

    if (activePlatforms.length <= 1) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    cycleTimer = setInterval(() => {
      cycleIdx = (cycleIdx + 1) % activePlatforms.length;
      showLogoForPlatform(activePlatforms[cycleIdx], true);
    }, 2200);
  }

  // ── Hero Active Engine Stack & Documentation Examples ───────────────────────
  function getSelectedPlatform() {
    return (
      activePlatforms.find((p) => p.key === selectedPlatformKey) ||
      activePlatforms[0] ||
      platformsList[0] ||
      { key: 'flipkart', label: 'Flipkart', service_code: 'xt' }
    );
  }

  function renderHeroStack() {
    if (!el.heroServiceStack) return;
    el.heroServiceStack.innerHTML = activePlatforms
      .map((p) => {
        const isCurrent = p.key === selectedPlatformKey;
        const imgHtml = p.logo ? `<img src="${escapeHtml(p.logo)}" alt="${escapeHtml(p.label)}">` : '';
        return `
          <button type="button" class="stack-chip ${isCurrent ? 'is-current' : ''}" data-select-platform="${escapeHtml(p.key)}">
            ${imgHtml}
            <span>${escapeHtml(p.label)}</span>
            <span class="chip-code">${escapeHtml(p.service_code || '')}</span>
          </button>`;
      })
      .join('');

    el.heroServiceStack.querySelectorAll('[data-select-platform]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.selectPlatform;
        selectedPlatformKey = key;
        const found = activePlatforms.find((x) => x.key === key);
        if (found) showLogoForPlatform(found, true);
        renderHeroStack();
        renderPurchaseDocs();
      });
    });
  }

  function renderPurchaseDocs() {
    const p = getSelectedPlatform();
    const payloadObj = {
      platform: p.key,
      target_status: 'NOT_REGISTERED',
      service_code: p.service_code || '',
      country_code: '22',
      max_attempts: 5,
    };
    const payloadPretty = JSON.stringify(payloadObj, null, 2);
    const url = `${ORIGIN}/api/v1/purchase`;

    if (el.codePurchaseReq) {
      if (activeLang === 'curl') {
        el.codePurchaseReq.textContent =
`curl -X POST "${url}" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: YOUR_SERVER_API_KEY" \\
  -H "X-NexNum-Key: YOUR_NEXNUM_KEY" \\
  -d '${JSON.stringify(payloadObj)}'`;
      } else if (activeLang === 'python') {
        el.codePurchaseReq.textContent =
`import requests

resp = requests.post(
    "${url}",
    headers={
        "X-API-Key": "YOUR_SERVER_API_KEY",
        "X-NexNum-Key": "YOUR_NEXNUM_KEY",
    },
    json=${payloadPretty},
    timeout=60,
)
print(resp.status_code, resp.json())`;
      } else {
        el.codePurchaseReq.textContent =
`const resp = await fetch("${url}", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": "YOUR_SERVER_API_KEY",
    "X-NexNum-Key": "YOUR_NEXNUM_KEY",
  },
  body: JSON.stringify(${payloadPretty}),
});
const data = await resp.json();`;
      }
    }

    if (el.docDefaultPlatform) el.docDefaultPlatform.textContent = `"${p.key}"`;

    if (el.docPlatformListDesc && platformsList.length) {
      const activeNames = activePlatforms.map((x) => `<code>${escapeHtml(x.key)}</code>`).join(', ');
      const disabledNames = platformsList.filter((x) => x.status !== 'active').map((x) => `<code>${escapeHtml(x.key)}</code>`).join(', ');
      el.docPlatformListDesc.innerHTML =
        `Active checker slug: ${activeNames}.` +
        (disabledNames ? ` (Disabled: ${disabledNames}).` : '');
    }

    if (el.docServiceMapDesc && platformsList.length) {
      const defaults = platformsList
        .map((x) => `${escapeHtml(x.key)}=<code>${escapeHtml(x.service_code || '—')}</code>`)
        .join(', ');
      el.docServiceMapDesc.innerHTML = `NexNum service code override (defaults: ${defaults}).`;
    }

    if (el.codePurchaseOk) {
      el.codePurchaseOk.textContent = JSON.stringify({
        success: true,
        order_id: '1791225496122425077082',
        phone_number: '919876543210',
        clean_mobile: '9876543210',
        platform: p.key,
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
      }, null, 2);
    }
  }

  function renderEnginesTable() {
    if (!el.enginesTableBody) return;
    if (!platformsList.length) {
      el.enginesTableBody.innerHTML = '<tr><td colspan="4">No engines returned by /api/platforms.</td></tr>';
      return;
    }

    el.enginesTableBody.innerHTML = platformsList
      .map((p) => {
        const isActive = p.status === 'active';
        const badge = isActive
          ? '<span class="auth-badge active">ACTIVE</span>'
          : '<span class="auth-badge disabled">DISABLED</span>';
        const logoImg = p.logo ? `<img src="${escapeHtml(p.logo)}" alt="${escapeHtml(p.label)}">` : '';
        return `
          <tr>
            <td><div class="engine-name-cell">${logoImg}<span>${escapeHtml(p.label)}</span></div></td>
            <td>${badge}</td>
            <td><code>${escapeHtml(p.service_code || '—')}</code></td>
            <td><code>${escapeHtml(p.module || '')}</code> — ${escapeHtml(p.mechanism || '')}</td>
          </tr>`;
      })
      .join('');
  }

  el.codeTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      el.codeTabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      activeLang = tab.dataset.lang;
      renderPurchaseDocs();
    });
  });

  el.copyReqBtn?.addEventListener('click', () => {
    if (el.codePurchaseReq) copyText(el.codePurchaseReq.textContent, 'Request snippet copied!');
  });

  async function hydrate() {
    try {
      const res = await fetch('/api/platforms');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      platformsList = Array.isArray(data.platforms) ? data.platforms : [];
      activePlatforms = platformsList.filter((p) => p.status === 'active');

      if (!selectedPlatformKey && activePlatforms.length) {
        selectedPlatformKey = activePlatforms[0].key;
      }

      startLogoCycler();
      renderHeroStack();
      renderPurchaseDocs();
      renderEnginesTable();
    } catch (err) {
      if (el.cyclingServiceLabel) el.cyclingServiceLabel.textContent = 'API Reference';
      if (el.enginesTableBody) {
        el.enginesTableBody.innerHTML = `<tr><td colspan="4" style="color:var(--red);">Failed to load /api/platforms: ${escapeHtml(err.message)}</td></tr>`;
      }
    }

    try {
      const res = await fetch('/api/health');
      if (!res.ok) throw new Error();
      const data = await res.json();
      if (el.liveHealthPill) el.liveHealthPill.className = 'health-pill online';
      if (el.liveHealthText) el.liveHealthText.textContent = 'LIVE v' + (data.version || '3.0.0');
    } catch {
      if (el.liveHealthPill) el.liveHealthPill.className = 'health-pill offline';
      if (el.liveHealthText) el.liveHealthText.textContent = 'OFFLINE';
    }
  }

  hydrate();
})();
