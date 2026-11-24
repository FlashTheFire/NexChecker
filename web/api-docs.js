/**
 * NexChecker — Minimal Dynamic API Reference Engine
 * Auto-cycles header brand logo across all live active platforms
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
    zomato:    { accent: '#E23744', soft: 'rgba(226,55,68,0.13)',  glow: 'rgba(226,55,68,0.28)' },
    flipkart:  { accent: '#3b82f6', soft: 'rgba(59,130,246,0.13)', glow: 'rgba(59,130,246,0.28)' },
    meesho:    { accent: '#a855f7', soft: 'rgba(168,85,247,0.13)', glow: 'rgba(168,85,247,0.28)' },
    myntra:    { accent: '#f43f5e', soft: 'rgba(244,63,94,0.13)',  glow: 'rgba(244,63,94,0.28)' },
    amazon:    { accent: '#f59e0b', soft: 'rgba(245,158,11,0.13)', glow: 'rgba(245,158,11,0.28)' },
    swiggy:    { accent: '#fb923c', soft: 'rgba(251,146,60,0.13)', glow: 'rgba(251,146,60,0.28)' },
    bigbasket: { accent: '#84cc16', soft: 'rgba(132,204,22,0.13)', glow: 'rgba(132,204,22,0.28)' },
    zepto:     { accent: '#c084fc', soft: 'rgba(192,132,252,0.13)',glow: 'rgba(192,132,252,0.28)' },
  };

  let platformsList = [];
  let activePlatforms = [];
  let selectedPlatformKey = '';
  let cycleIdx = 0;
  let cycleTimer = null;
  let transitionIdx = 0;
  let transitionCleanupTimer = null;
  let labelSwapTimer = null;
  let activeLang = 'curl';

  const TRANSITIONS = ['wipe', 'dissolve', 'crosscut', 'spin', 'cutaway'];

  const el = {
    sidebar: document.getElementById('docsSidebar'),
    backdrop: document.getElementById('sidebarBackdrop'),
    menuToggle: document.getElementById('menuToggle'),
    drawerCloseBtn: document.getElementById('drawerCloseBtn'),
    navLinks: document.querySelectorAll('#topNav .nav-link, #sidebarNav .nav-link'),

    brandMark: document.querySelector('.brand-mark'),
    dynamicLogoImg: document.getElementById('dynamicLogoImg'),
    dynamicLogoImgStage: document.getElementById('dynamicLogoImgStage'),
    logoDissolveFlash: document.getElementById('logoDissolveFlash'),
    dynamicLogoFallback: document.getElementById('dynamicLogoFallback'),
    cyclingServiceLabel: document.getElementById('cyclingServiceLabel'),
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

  function tok(cls, text) {
    return `<span class="${cls}">${escapeHtml(text)}</span>`;
  }

  // Single-pass VS Code Dark+ JSON highlighter
  function highlightJSON(jsonText) {
    const tokenRe = /("(?:\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(?:\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?|[{}\[\],:])/g;
    let out = '';
    let lastIdx = 0;

    for (const m of jsonText.matchAll(tokenRe)) {
      if (m.index > lastIdx) out += escapeHtml(jsonText.slice(lastIdx, m.index));
      const t = m[0];

      if (t.startsWith('"')) {
        if (t.endsWith(':')) {
          const colonIdx = t.lastIndexOf(':');
          out += tok('tok-key', t.slice(0, colonIdx)) + tok('tok-punc', t.slice(colonIdx));
        } else {
          out += tok('tok-str', t);
        }
      } else if (t === 'true' || t === 'false' || t === 'null') {
        out += tok('tok-bool', t);
      } else if (t === '{' || t === '}') {
        out += tok('tok-brk1', t);
      } else if (t === '[' || t === ']') {
        out += tok('tok-brk2', t);
      } else if (t === ',' || t === ':') {
        out += tok('tok-punc', t);
      } else {
        out += tok('tok-num', t);
      }
      lastIdx = m.index + t.length;
    }

    if (lastIdx < jsonText.length) out += escapeHtml(jsonText.slice(lastIdx));
    return out;
  }

  // Single-pass VS Code Dark+ Code highlighter (cURL, Python, JS)
  function highlightCode(codeText, lang) {
    if (lang === 'curl') {
      const re = /('(?:\\'|[^'])*')|("(?:\\"|[^"])*")|\b(curl)\b|\b(GET|POST|PUT|DELETE|PATCH)\b|(\s-[A-Za-z-]+)|(\\$)/gm;
      let out = '';
      let lastIdx = 0;
      for (const m of codeText.matchAll(re)) {
        if (m.index > lastIdx) out += escapeHtml(codeText.slice(lastIdx, m.index));
        const [full, sq, dq, cmd, verb, flag, cont] = m;
        if (sq) {
          const inner = sq.slice(1, -1);
          const highlightedInner = inner.trim().startsWith('{') ? highlightJSON(inner) : escapeHtml(inner);
          out += tok('tok-str', "'") + highlightedInner + tok('tok-str', "'");
        } else if (dq) {
          out += tok('tok-str', dq);
        } else if (cmd) {
          out += tok('tok-fn', cmd);
        } else if (verb) {
          out += tok('tok-type', verb);
        } else if (flag) {
          out += tok('tok-kw', flag);
        } else if (cont) {
          out += tok('tok-punc', cont);
        } else {
          out += escapeHtml(full);
        }
        lastIdx = m.index + full.length;
      }
      if (lastIdx < codeText.length) out += escapeHtml(codeText.slice(lastIdx));
      return out;
    }

    if (lang === 'python') {
      const re = /(#.*$)|("(?:\\"|[^"])*"(?:\s*:)?|'(?:\\'|[^'])*'(?:\s*:)?)|\b(import|from|as|return|if|else|await|async)\b|\b(True|False|None|def|class)\b|(\b[a-z_][a-zA-Z0-9_]*(?=\s*=[^=]))|\b(requests|json)\b|\b(post|get|print)\b|(\b\d+(?:\.\d+)?\b)|([{}()\[\],:])/gm;
      let out = '';
      let lastIdx = 0;
      for (const m of codeText.matchAll(re)) {
        if (m.index > lastIdx) out += escapeHtml(codeText.slice(lastIdx, m.index));
        const [full, comm, str, ctrl, kw, ident, mod, fn, num, punc] = m;
        if (comm) out += tok('tok-comm', comm);
        else if (str) {
          if (str.endsWith(':')) {
            const cIdx = str.lastIndexOf(':');
            out += tok('tok-key', str.slice(0, cIdx)) + tok('tok-punc', str.slice(cIdx));
          } else {
            out += tok('tok-str', str);
          }
        }
        else if (ctrl) out += tok('tok-ctrl', ctrl);
        else if (kw) out += tok('tok-kw', kw);
        else if (ident) out += tok('tok-var', ident);
        else if (mod) out += tok('tok-type', mod);
        else if (fn) out += tok('tok-fn', fn);
        else if (num) out += tok('tok-num', num);
        else if (punc === '{' || punc === '}') out += tok('tok-brk1', punc);
        else if (punc === '[' || punc === ']') out += tok('tok-brk2', punc);
        else if (punc) out += tok('tok-punc', punc);
        else out += escapeHtml(full);
        lastIdx = m.index + full.length;
      }
      if (lastIdx < codeText.length) out += escapeHtml(codeText.slice(lastIdx));
      return out;
    }

    // JavaScript
    const re = /(\/\/.*$)|("(?:\\"|[^"])*"(?:\s*:)?|'(?:\\'|[^'])*'(?:\s*:)?|`(?:\\`|[^`])*`)|\b(await|return|import|from|export|if|else)\b|\b(const|let|var|async|function|true|false|null)\b|\b(JSON|console|Response)\b|\b(fetch|stringify|json|log)\b|(\b[a-zA-Z_][a-zA-Z0-9_]*(?=\s*:))|(\b\d+(?:\.\d+)?\b)|([{}()\[\],;:])/gm;
    let out = '';
    let lastIdx = 0;
    for (const m of codeText.matchAll(re)) {
      if (m.index > lastIdx) out += escapeHtml(codeText.slice(lastIdx, m.index));
      const [full, comm, str, ctrl, kw, cls, fn, prop, num, punc] = m;
      if (comm) out += tok('tok-comm', comm);
      else if (str) {
        if (str.endsWith(':')) {
          const cIdx = str.lastIndexOf(':');
          out += tok('tok-key', str.slice(0, cIdx)) + tok('tok-punc', str.slice(cIdx));
        } else {
          out += tok('tok-str', str);
        }
      }
      else if (ctrl) out += tok('tok-ctrl', ctrl);
      else if (kw) out += tok('tok-kw', kw);
      else if (cls) out += tok('tok-type', cls);
      else if (fn) out += tok('tok-fn', fn);
      else if (prop) out += tok('tok-var', prop);
      else if (num) out += tok('tok-num', num);
      else if (punc === '{' || punc === '}') out += tok('tok-brk1', punc);
      else if (punc === '[' || punc === ']') out += tok('tok-brk2', punc);
      else if (punc) out += tok('tok-punc', punc);
      else out += escapeHtml(full);
      lastIdx = m.index + full.length;
    }
    if (lastIdx < codeText.length) out += escapeHtml(codeText.slice(lastIdx));
    return out;
  }

  function renderCodeLines(preEl, highlightedHtml, rawCode) {
    if (!preEl) return;
    preEl.dataset.rawCode = rawCode;
    const rawLines = highlightedHtml.split('\n');
    const openTags = [];

    const htmlLines = rawLines.map((lineHtml, idx) => {
      const prefix = openTags.join('');
      const tagRe = /<\/?span(?:\s+class="[^"]*")?>/g;
      for (const m of lineHtml.matchAll(tagRe)) {
        if (m[0] === '</span>') {
          openTags.pop();
        } else {
          openTags.push(m[0]);
        }
      }
      const suffix = '</span>'.repeat(openTags.length);
      return `<div class="code-line"><span class="line-num" aria-hidden="true">${idx + 1}</span><span class="line-code">${prefix}${lineHtml}${suffix}</span></div>`;
    });

    preEl.innerHTML = htmlLines.join('');
  }

  function showToast(msg) {
    if (!el.toast) return;
    el.toast.textContent = msg;
    el.toast.classList.add('show');
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => el.toast.classList.remove('show'), 1600);
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

  // ── Fixed Responsive Hamburger Drawer & Header Scroll Spy ──────────────────
  function toggleSidebar(forceOpen) {
    if (!el.sidebar) return;
    const open = typeof forceOpen === 'boolean' ? forceOpen : !el.sidebar.classList.contains('open');
    el.sidebar.classList.toggle('open', open);
    el.backdrop?.classList.toggle('open', open);
    el.backdrop?.setAttribute('aria-hidden', String(!open));
    el.menuToggle?.classList.toggle('is-open', open);
    el.menuToggle?.setAttribute('aria-expanded', String(open));
    document.body.classList.toggle('drawer-open', open);
  }

  el.menuToggle?.addEventListener('click', () => toggleSidebar());
  el.drawerCloseBtn?.addEventListener('click', () => toggleSidebar(false));
  el.backdrop?.addEventListener('click', () => toggleSidebar(false));
  el.navLinks.forEach((link) => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 960) toggleSidebar(false);
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && el.sidebar?.classList.contains('open')) {
      toggleSidebar(false);
      el.menuToggle?.focus();
    }
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 960 && el.sidebar?.classList.contains('open')) {
      toggleSidebar(false);
    }
  }, { passive: true });

  const sections = document.querySelectorAll('section.doc-section, h3[id]');
  window.addEventListener('scroll', () => {
    let currentId = 'ep-purchase';
    const scrollPos = window.scrollY + 120;
    sections.forEach((sec) => {
      if (sec.offsetTop <= scrollPos && sec.id) currentId = sec.id;
    });
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 24 && sections.length) {
      const last = sections[sections.length - 1];
      if (last.id) currentId = last.id;
    }
    el.navLinks.forEach((lnk) => {
      lnk.classList.toggle('active', lnk.getAttribute('href') === '#' + currentId);
    });
  }, { passive: true });

  document.querySelectorAll('.copy-code-btn[data-copy-target]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.copyTarget);
      if (target) copyText(target.dataset.rawCode || target.textContent, 'Copied!');
    });
  });

  // ── Auto-Cycling Active Service Main Logo ───────────────────────────────────
  function applyBrandAccent(key) {
    const palette = BRAND_ACCENTS[key] || BRAND_ACCENTS.flipkart;
    const root = document.documentElement.style;
    root.setProperty('--accent', palette.accent);
    root.setProperty('--accent-soft', palette.soft);
    root.setProperty('--accent-glow', palette.glow);
  }

  const TR_CLASSES = [
    'is-front', 'is-stage',
    'tr-wipe-out', 'tr-wipe-in',
    'tr-dissolve-out', 'tr-dissolve-in',
    'tr-crosscut-out', 'tr-crosscut-in',
    'tr-spin-out', 'tr-spin-in',
    'tr-cutaway-out', 'tr-cutaway-in',
  ];

  function clearTransitionClasses(imgEl) {
    if (imgEl) imgEl.classList.remove(...TR_CLASSES);
  }

  function showLogoForPlatform(p, animate = true) {
    if (!p || !el.dynamicLogoImg || !el.cyclingServiceLabel) return;

    const front = el.dynamicLogoImg;
    const stage = el.dynamicLogoImgStage;

    if (!animate || !stage || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      if (transitionCleanupTimer) clearTimeout(transitionCleanupTimer);
      if (labelSwapTimer) clearTimeout(labelSwapTimer);
      clearTransitionClasses(front);
      clearTransitionClasses(stage);
      if (stage) stage.classList.add('is-hidden');
      if (p.logo) {
        front.src = p.logo;
        front.alt = '';
        front.classList.remove('is-hidden');
        front.classList.add('is-front');
        if (el.dynamicLogoFallback) el.dynamicLogoFallback.style.display = 'none';
      } else {
        front.classList.add('is-hidden');
        if (el.dynamicLogoFallback) el.dynamicLogoFallback.style.display = 'block';
      }
      el.cyclingServiceLabel.textContent = p.label;
      applyBrandAccent(p.key);
      return;
    }

    // Dual-frame editorial transition (Wipe / Additive Dissolve / Cross-Cut / Spin / Cutaway)
    if (transitionCleanupTimer) {
      clearTimeout(transitionCleanupTimer);
      if (!stage.classList.contains('is-hidden') && stage.src) {
        front.src = stage.src;
        front.classList.remove('is-hidden');
      }
    }
    if (labelSwapTimer) clearTimeout(labelSwapTimer);
    clearTransitionClasses(front);
    clearTransitionClasses(stage);
    el.logoDissolveFlash?.classList.remove('is-flashing');

    const tr = TRANSITIONS[transitionIdx % TRANSITIONS.length];
    transitionIdx++;

    // Prepare incoming image on stage layer
    if (p.logo) {
      stage.src = p.logo;
      stage.alt = '';
      stage.classList.remove('is-hidden');
      if (el.dynamicLogoFallback) el.dynamicLogoFallback.style.display = 'none';
    } else {
      stage.classList.add('is-hidden');
    }

    front.classList.add('is-front');
    stage.classList.add('is-stage');

    // Reflow to restart keyframe animations reliably
    void stage.offsetWidth;

    front.classList.add(`tr-${tr}-out`);
    stage.classList.add(`tr-${tr}-in`);
    if (tr === 'dissolve' && el.logoDissolveFlash) {
      void el.logoDissolveFlash.offsetWidth;
      el.logoDissolveFlash.classList.add('is-flashing');
    }

    // Kinetic vertical ticker on service label
    el.cyclingServiceLabel.classList.remove('label-in', 'label-out');
    void el.cyclingServiceLabel.offsetWidth;
    el.cyclingServiceLabel.classList.add('label-out');

    labelSwapTimer = setTimeout(() => {
      el.cyclingServiceLabel.textContent = p.label;
      el.cyclingServiceLabel.classList.remove('label-out');
      el.cyclingServiceLabel.classList.add('label-in');
    }, 150);

    applyBrandAccent(p.key);

    transitionCleanupTimer = setTimeout(() => {
      if (p.logo) {
        front.src = p.logo;
        front.classList.remove('is-hidden');
      }
      clearTransitionClasses(front);
      clearTransitionClasses(stage);
      front.classList.add('is-front');
      stage.classList.add('is-hidden');
      el.logoDissolveFlash?.classList.remove('is-flashing');
      el.cyclingServiceLabel.classList.remove('label-in', 'label-out');
      transitionCleanupTimer = null;
    }, 430);
  }

  function startLogoCycler() {
    if (cycleTimer) clearInterval(cycleTimer);
    if (!activePlatforms.length) return;

    activePlatforms.forEach((p) => {
      if (p.logo) { const img = new Image(); img.src = p.logo; }
    });

    showLogoForPlatform(activePlatforms[0], false);

    if (activePlatforms.length <= 1) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const scheduleNext = () => {
      if (cycleTimer) clearInterval(cycleTimer);
      cycleTimer = setInterval(() => {
        if (document.hidden) return;
        cycleIdx = (cycleIdx + 1) % activePlatforms.length;
        showLogoForPlatform(activePlatforms[cycleIdx], true);
      }, 2300);
    };

    scheduleNext();

    // Pause cleanly on hover for inspection
    el.brandMark?.addEventListener('mouseenter', () => {
      if (cycleTimer) clearInterval(cycleTimer);
    });
    el.brandMark?.addEventListener('mouseleave', scheduleNext);
  }

  // ── Dynamic Purchase Examples & Engine Table ────────────────────────────────
  function getSelectedPlatform() {
    return (
      activePlatforms.find((p) => p.key === selectedPlatformKey) ||
      activePlatforms[0] ||
      platformsList[0] ||
      { key: 'flipkart', label: 'Flipkart', service_code: 'xt' }
    );
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
      let rawCode = '';
      if (activeLang === 'curl') {
        rawCode =
`curl -X POST "${url}" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: YOUR_SERVER_API_KEY" \\
  -H "X-NexNum-Key: YOUR_NEXNUM_KEY" \\
  -d '${payloadPretty}'`;
      } else if (activeLang === 'python') {
        rawCode =
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
        rawCode =
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
      renderCodeLines(el.codePurchaseReq, highlightCode(rawCode, activeLang), rawCode);
    }

    if (el.docDefaultPlatform) el.docDefaultPlatform.textContent = `"${p.key}"`;

    if (el.docPlatformListDesc && platformsList.length) {
      const activeCodes = activePlatforms.map((x) => `<code>${escapeHtml(x.key)}</code>`).join(', ');
      el.docPlatformListDesc.innerHTML = `Active: ${activeCodes}.`;
    }

    if (el.docServiceMapDesc && platformsList.length) {
      const defaults = platformsList
        .map((x) => `${escapeHtml(x.key)}=<code>${escapeHtml(x.service_code || '—')}</code>`)
        .join(', ');
      el.docServiceMapDesc.innerHTML = defaults;
    }

    if (el.codePurchaseOk) {
      const jsonStr = JSON.stringify({
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
      renderCodeLines(el.codePurchaseOk, highlightJSON(jsonStr), jsonStr);
    }
  }

  function renderEnginesTable() {
    if (!el.enginesTableBody) return;
    if (!platformsList.length) {
      el.enginesTableBody.innerHTML = '<tr><td colspan="3">No engines available.</td></tr>';
      return;
    }

    el.enginesTableBody.innerHTML = platformsList
      .map((p) => {
        const isActive = p.status === 'active';
        const badge = isActive
          ? '<span class="auth-badge active">ACTIVE</span>'
          : '<span class="auth-badge disabled">DISABLED</span>';
        const logoImg = p.logo ? `<img src="${escapeHtml(p.logo)}" alt="">` : '';
        return `
          <tr ${isActive ? `data-engine-key="${escapeHtml(p.key)}" style="cursor:pointer;" title="Click to preview ${escapeHtml(p.label)} payload"` : ''}>
            <td><div class="engine-name-cell">${logoImg}<span>${escapeHtml(p.label)}</span></div></td>
            <td>${badge}</td>
            <td><code>${escapeHtml(p.service_code || '—')}</code></td>
          </tr>`;
      })
      .join('');

    el.enginesTableBody.querySelectorAll('[data-engine-key]').forEach((row) => {
      row.addEventListener('click', () => {
        selectedPlatformKey = row.dataset.engineKey;
        const found = activePlatforms.find((x) => x.key === selectedPlatformKey);
        if (found) showLogoForPlatform(found, true);
        renderPurchaseDocs();
        showToast(`Switched example to ${selectedPlatformKey}`);
      });
    });
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
    if (el.codePurchaseReq) copyText(el.codePurchaseReq.dataset.rawCode || el.codePurchaseReq.textContent, 'Copied!');
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
      renderPurchaseDocs();
      renderEnginesTable();
    } catch (err) {
      if (el.cyclingServiceLabel) el.cyclingServiceLabel.textContent = 'API Reference';
      if (el.enginesTableBody) {
        el.enginesTableBody.innerHTML = `<tr><td colspan="3" style="color:var(--red);">Failed to load /api/platforms: ${escapeHtml(err.message)}</td></tr>`;
      }
    }
  }

  hydrate();
})();
