/**
 * NexChecker — Multi-Brand Adaptive Application Engine
 * Dark Mode · 8 Brand Themes · Full Micro-Interactions
 * 
 * CDN: Fluent Animated Emoji (bignutty/fluent-emoji)
 * URL: https://raw.githubusercontent.com/bignutty/fluent-emoji/main/animated/{unicode}.png
 */

(function () {
  'use strict';

  // ── Telegram WebApp Init ─────────────────────────────────────────────────────
  const tg = window.Telegram?.WebApp;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.isVersionAtLeast && tg.isVersionAtLeast('6.2') && tg.enableClosingConfirmation) {
        tg.enableClosingConfirmation();
      }
    } catch (e) { /* non-blocking */ }
  }

  // ── Cryptographic Security & Auth Headers ────────────────────────────────────
  function getGuestId() {
    let gid = localStorage.getItem('nex_guest_id');
    if (!gid) {
      gid = 'g_' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
      localStorage.setItem('nex_guest_id', gid);
    }
    return gid;
  }

  function getAuthHeaders() {
    const headers = {
      'Content-Type': 'application/json',
      'X-Guest-ID': getGuestId(),
    };
    if (window.Telegram?.WebApp?.initData) {
      headers['X-Telegram-Init-Data'] = window.Telegram.WebApp.initData;
    }
    return headers;
  }

  async function apiFetch(url, options = {}) {
    const defaultHeaders = getAuthHeaders();
    const mergedHeaders = { ...defaultHeaders, ...(options.headers || {}) };
    const res = await fetch(url, { ...options, headers: mergedHeaders });
    if (res.status === 401) {
      enforceTelegramSecurity();
    }
    return res;
  }

  // ── Cryptographic Security Gate Enforcer ────────────────────────────────────
  async function enforceTelegramSecurity() {
    const gate = document.getElementById('securityGate');
    const app = document.getElementById('app');
    const gateTitle = document.getElementById('gateTitle');
    const gateDesc = document.getElementById('gateDesc');

    const initData = window.Telegram?.WebApp?.initData || '';

    // Direct browser visit without Telegram WebApp context
    if (!initData) {
      if (gate) gate.style.display = 'flex';
      if (app) app.style.display = 'none';
      return false;
    }

    // Cryptographic validation with server backend
    try {
      const resp = await fetch('/api/auth/verify', {
        headers: { 'X-Telegram-Init-Data': initData }
      });
      const data = await resp.json();

      if (data.authenticated && data.user) {
        // Unlock application securely
        if (gate) gate.style.display = 'none';
        if (app) app.style.display = 'block';

        const user = data.user;
        const displayName = user.username ? `@${user.username}` : (user.first_name || 'Verified User');
        const locSub = document.querySelector('.loc-subtitle');
        if (locSub) locSub.textContent = `0-OTP Verified • ${displayName}`;
        return true;
      } else {
        // Signature expired or failed HMAC check
        if (gate) gate.style.display = 'flex';
        if (app) app.style.display = 'none';
        if (gateDesc) {
          gateDesc.textContent = data.status === 'EXPIRED'
            ? 'Telegram session expired. Tap below to reopen inside @NexChecker_Robot.'
            : (data.message || 'Please open via @NexChecker_Robot to start.');
        }
        return false;
      }
    } catch (err) {
      if (gate) gate.style.display = 'flex';
      if (app) app.style.display = 'none';
      return false;
    }
  }

  // ── CDN & Fluent Emoji Utilities ─────────────────────────────────────────────
  const FLUENT_CDN = 'https://cdn.jsdelivr.net/gh/bignutty/fluent-emoji@main/animated-static';

  const EMOJI_MAP = {
    '✅': '2705.png',
    '✨': '2728.png',
    '🍽': '1f37d-fe0f.png',
    '🍽️': '1f37d-fe0f.png',
    '📦': '1f4e6.png',
    '🥬': '1f96c.png',
    '👗': '1f457.png',
    '🛵': '1f6f5.png',
    '🛍': '1f6cd-fe0f.png',
    '🛍️': '1f6cd-fe0f.png',
    '⚡': '26a1.png',
    '🌱': '1f331.png',
    '🔍': '1f50d.png',
    '🎉': '1f389.png',
    '🔥': '1f525.png',
    '🛒': '1f6d2.png',
    '👜': '1f45c.png',
    '🚀': '1f680.png',
  };

  function fluentUrl(emoji) {
    if (!emoji) return null;
    if (typeof emoji === 'string') {
      if (emoji.endsWith('.png')) return `${FLUENT_CDN}/${emoji}`;
      if (/^[0-9a-fA-F\-]+$/.test(emoji)) return `${FLUENT_CDN}/${emoji.toLowerCase()}.png`;
    }
    if (EMOJI_MAP[emoji]) {
      return `${FLUENT_CDN}/${EMOJI_MAP[emoji]}`;
    }
    try {
      const cp = emoji.codePointAt(0);
      return cp ? `${FLUENT_CDN}/${cp.toString(16).toLowerCase()}.png` : null;
    } catch {
      return null;
    }
  }

  // ── Brand Configuration ──────────────────────────────────────────────────────
  const BRANDS = {
    zomato: {
      name: 'Zomato',
      logo: '/static/src/logos/zomato.png',
      primary: '#E23744',
      emoji: '🍽',
      scanEmoji: '🍽',
      registeredEmoji: '✅',
      freshEmoji: '✨',
      bannerTitle: 'Zomato Account Checker',
      bannerSubtitle: 'Food & dining platform lookup',
      demoRegistered: '7631328516',
      demoFresh: '7005999888',
      ctaLabel: 'Check on Zomato',
      scanSteps: [
        'Connecting to Zomato Sushi API...',
        'Authenticating OTP session...',
        'Probing account registry...',
        'Resolving registration status...',
      ],
      resultDescriptions: {
        registered: 'Account exists on Zomato',
        fresh: 'No account found — fresh number',
      }
    },
    flipkart: {
      name: 'Flipkart',
      logo: '/static/src/logos/flipkart.png',
      primary: '#2874F0',
      emoji: '🛍',
      scanEmoji: '🛍',
      registeredEmoji: '✅',
      freshEmoji: '✨',
      bannerTitle: 'Flipkart Account Checker',
      bannerSubtitle: 'Direct platform registry lookup',
      demoRegistered: '9999999999',
      demoFresh: '8888888888',
      ctaLabel: 'Check on Flipkart',
      scanSteps: [
        'Connecting to Flipkart registry...',
        'Querying customer database...',
        'Checking account existence...',
        'Verifying user registration...',
      ],
      resultDescriptions: {
        registered: 'Account exists on Flipkart',
        fresh: 'No account found — fresh number',
      }
    },
    meesho: {
      name: 'Meesho',
      logo: '/static/src/logos/meesho.png',
      primary: '#9b3af7',
      emoji: '🛒',
      scanEmoji: '🛒',
      registeredEmoji: '✅',
      freshEmoji: '🌱',
      bannerTitle: 'Meesho Account Checker',
      bannerSubtitle: 'Jamuni-powered silent verification',
      demoRegistered: '9876543210',
      demoFresh: '7005999888',
      ctaLabel: 'Check on Meesho',
      scanSteps: [
        'Connecting to Meesho API...',
        'Initializing Jamuni protocol...',
        'Probing reseller registry...',
        'Resolving account status...',
      ],
      resultDescriptions: {
        registered: 'Account exists on Meesho',
        fresh: 'No account — fresh for reseller signup',
      }
    },
    bigbasket: {
      name: 'BigBasket',
      logo: '/static/src/logos/bigbasket.png',
      primary: '#A6CE39',
      emoji: '🥬',
      scanEmoji: '🥬',
      registeredEmoji: '✅',
      freshEmoji: '✨',
      bannerTitle: 'BigBasket Account Checker',
      bannerSubtitle: 'Grocery platform registry lookup',
      demoRegistered: '9999999991',
      demoFresh: '8888888881',
      ctaLabel: 'Check on BigBasket',
      scanSteps: [
        'Connecting to BigBasket registry...',
        'Querying grocery account DB...',
        'Checking membership status...',
        'Verifying account existence...',
      ],
      resultDescriptions: {
        registered: 'Account exists on BigBasket',
        fresh: 'No account — fresh grocery number',
      }
    },
    myntra: {
      name: 'Myntra',
      logo: '/static/src/logos/myntra.png',
      primary: '#FF3F6C',
      emoji: '👜',
      scanEmoji: '👜',
      registeredEmoji: '✅',
      freshEmoji: '✨',
      bannerTitle: 'Myntra Account Checker',
      bannerSubtitle: 'Fashion platform account lookup',
      demoRegistered: '9999999992',
      demoFresh: '8888888882',
      ctaLabel: 'Check on Myntra',
      scanSteps: [
        'Connecting to Myntra registry...',
        'Querying fashion account DB...',
        'Checking shopper profile...',
        'Verifying account status...',
      ],
      resultDescriptions: {
        registered: 'Account exists on Myntra',
        fresh: 'No account — fresh fashion number',
      }
    },
    swiggy: {
      name: 'Swiggy',
      logo: '/static/src/logos/swiggy.png',
      primary: '#FC8019',
      emoji: '🛵',
      scanEmoji: '🛵',
      registeredEmoji: '✅',
      freshEmoji: '✨',
      bannerTitle: 'Swiggy Account Checker',
      bannerSubtitle: 'Super-fast delivery account lookup',
      demoRegistered: '9999999993',
      demoFresh: '8888888883',
      ctaLabel: 'Check on Swiggy',
      scanSteps: [
        'Connecting to Swiggy platform...',
        'Initializing delivery API...',
        'Probing customer registry...',
        'Verifying account existence...',
      ],
      resultDescriptions: {
        registered: 'Account exists on Swiggy',
        fresh: 'No account — fresh delivery number',
      }
    },
    zepto: {
      name: 'Zepto',
      logo: '/static/src/logos/zepto.png',
      primary: '#950EDB',
      emoji: '🚀',
      scanEmoji: '🚀',
      registeredEmoji: '✅',
      freshEmoji: '✨',
      bannerTitle: 'Zepto Account Checker',
      bannerSubtitle: '10-minute delivery account lookup',
      demoRegistered: '9999999994',
      demoFresh: '8888888884',
      ctaLabel: 'Check on Zepto',
      scanSteps: [
        'Connecting to Zepto registry...',
        'Querying quick-commerce DB...',
        'Checking customer profile...',
        'Verifying account status...',
      ],
      resultDescriptions: {
        registered: 'Account exists on Zepto',
        fresh: 'No account — fresh quick-commerce number',
      }
    },
    amazon: {
      name: 'Amazon',
      logo: '/static/src/logos/amazon.png',
      primary: '#FF9900',
      emoji: '📦',
      scanEmoji: '📦',
      registeredEmoji: '✅',
      freshEmoji: '✨',
      bannerTitle: 'Amazon Account Checker',
      bannerSubtitle: 'World\'s largest e-commerce lookup',
      demoRegistered: '9999999995',
      demoFresh: '8888888885',
      ctaLabel: 'Check on Amazon',
      scanSteps: [
        'Connecting to Amazon registry...',
        'Querying customer database...',
        'Checking Prime membership...',
        'Verifying account existence...',
      ],
      resultDescriptions: {
        registered: 'Account exists on Amazon India',
        fresh: 'No account — fresh Amazon number',
      }
    },
  };

  // ── App State ────────────────────────────────────────────────────────────────
  const state = {
    activeBrand: 'zomato',
    currentTab: 'single',
    history: JSON.parse(localStorage.getItem('nex_checker_history') || '[]'),
    batchResults: [],
    batchRunning: false,
    checkStartTime: 0,
    stats: {
      total_checks: 0,
      registered_checks: 0,
      fresh_checks: 0,
      platform_checks: {},
    },
  };

  // ── DOM Cache ────────────────────────────────────────────────────────────────
  const el = {
    app:               document.getElementById('app'),
    htmlRoot:          document.documentElement,
    brandFlash:        document.getElementById('brandFlash'),
    headerLogo:        document.getElementById('headerLogo'),
    heroBrandCard:     document.getElementById('heroBrandCard'),
    bannerEmoji:       document.getElementById('bannerEmoji'),
    bannerEmojiImg:    document.getElementById('bannerEmojiImg'),
    bannerEmojiFallback: document.getElementById('bannerEmojiFallback'),
    bannerTitle:       document.getElementById('bannerTitle'),
    bannerSubtitle:    document.getElementById('bannerSubtitle'),
    locAddressText:    document.getElementById('locAddressText'),

    modeTabs:          document.querySelectorAll('.mode-tab'),
    tabContents:       document.querySelectorAll('.tab-content'),
    bottomNavItems:    document.querySelectorAll('.b-nav-item'),

    mobileInput:       document.getElementById('mobileInput'),
    btnCheck:          document.getElementById('btnCheck'),
    ctaLabel:          document.getElementById('ctaLabel'),
    ctaSpinner:        document.getElementById('ctaSpinner'),
    btnPaste:          document.getElementById('btnPaste'),
    btnClear:          document.getElementById('btnClear'),
    btnDemoRegistered: document.getElementById('btnDemoRegistered'),
    btnDemoFresh:      document.getElementById('btnDemoFresh'),
    errorBanner:       document.getElementById('errorBanner'),
    scanningContainer: document.getElementById('scanningContainer'),
    scanStepText:      document.getElementById('scanStepText'),
    scanStepDetail:    document.getElementById('scanStepDetail'),
    scanEmojiImg:      document.getElementById('scanEmojiImg'),

    flipCardOuter:     document.getElementById('flipCardOuter'),
    flipCardInner:     document.getElementById('flipCardInner'),
    resultCard:        document.getElementById('resultCard'),
    resultHeader:      document.getElementById('resultHeader'),
    resultBrandLogo:   document.getElementById('resultBrandLogo'),
    resultBrandName:   document.getElementById('resultBrandName'),
    resultStatusBadge: document.getElementById('resultStatusBadge'),
    resultStatusIcon:  document.getElementById('resultStatusIcon'),
    resultStatusText:  document.getElementById('resultStatusText'),
    verdictTitle:      document.getElementById('verdictTitle'),
    verdictSubtitle:   document.getElementById('verdictSubtitle'),
    verdictEmojiImg:   document.getElementById('verdictEmojiImg'),
    verdictEmojiFallback: document.getElementById('verdictEmojiFallback'),
    resultPhoneNum:    document.getElementById('resultPhoneNum'),
    resultPhoneTap:    document.getElementById('resultPhoneTap'),
    resPlatformVal:    document.getElementById('resPlatformVal'),
    resStatusVal:      document.getElementById('resStatusVal'),
    resFreshVal:       document.getElementById('resFreshVal'),
    resTimeVal:        document.getElementById('resTimeVal'),
    btnRecheck:        document.getElementById('btnRecheck'),

    batchInput:        document.getElementById('batchInput'),
    btnBatchPaste:     document.getElementById('btnBatchPaste'),
    btnBatchClear:     document.getElementById('btnBatchClear'),
    btnBatchRun:       document.getElementById('btnBatchRun'),
    batchProgress:     document.getElementById('batchProgress'),
    batchProgressText: document.getElementById('batchProgressText'),
    batchProgressFill: document.getElementById('batchProgressFill'),
    batchResults:      document.getElementById('batchResults'),
    batchExportRow:    document.getElementById('batchExportRow'),
    btnBatchExport:    document.getElementById('btnBatchExport'),

    ptrIndicator:      document.getElementById('ptrIndicator'),
    historyList:       document.getElementById('historyList'),
    btnHistoryClear:   document.getElementById('btnHistoryClear'),

    confettiCanvas:    document.getElementById('confettiCanvas'),
    copyToast:         document.getElementById('copyToast'),
    engineStatus:      document.getElementById('engineStatus'),
    bannerStatsPills:  document.getElementById('bannerStatsPills'),
  };

  // ── Brand Switch ─────────────────────────────────────────────────────────────
  window.switchBrand = function (brandKey, chipEl) {
    if (state.activeBrand === brandKey) return;
    state.activeBrand = brandKey;
    const brand = BRANDS[brandKey];

    // 1) Flash overlay
    el.brandFlash.classList.add('flash');
    setTimeout(() => el.brandFlash.classList.remove('flash'), 200);

    // 2) Set data-brand on <html>
    el.htmlRoot.setAttribute('data-brand', brandKey);

    // 2b) Update header brand logo & wordmark
    if (el.headerLogo) {
      el.headerLogo.innerHTML = `<img src="${brand.logo}" alt="${brand.name}" style="height:26px; width:26px; object-fit:contain; border-radius:6px; margin-right:8px; vertical-align:middle; display:inline-block;" /><span style="font-size:17px; font-weight:800; letter-spacing:0.5px; color:var(--brand-header-text); line-height:1;">${brand.name.toUpperCase()}</span>`;
    }

    // 3) Update chips active state
    document.querySelectorAll('.service-chip').forEach(c => c.classList.remove('active'));
    if (chipEl) chipEl.classList.add('active');

    // 4) Update banner
    el.bannerTitle.textContent = brand.bannerTitle;
    el.bannerSubtitle.textContent = brand.bannerSubtitle;

    // 5) Update banner emoji (Fluent animated)
    const emojiUrl = fluentUrl(brand.emoji);
    if (emojiUrl) {
      el.bannerEmojiImg.src = emojiUrl;
      el.bannerEmojiImg.style.display = 'block';
      el.bannerEmojiFallback.style.display = 'none';
    } else {
      el.bannerEmojiImg.style.display = 'none';
      el.bannerEmojiFallback.textContent = brand.emoji;
      el.bannerEmojiFallback.style.display = 'flex';
    }

    // 6) Update scan emoji
    const scanUrl = fluentUrl(brand.emoji);
    if (scanUrl) { el.scanEmojiImg.src = scanUrl; }

    // 7) Update CTA label
    el.ctaLabel.textContent = brand.ctaLabel;

    // 8) Update demo buttons
    el.btnDemoRegistered.textContent = `🎯 Registered (${brand.demoRegistered.slice(-4)})`;
    el.btnDemoFresh.textContent = `✨ Fresh (${brand.demoFresh.slice(-4)})`;

    // 9) Haptic feedback
    haptic('selection');

    // 10) Restore hero input card and reset scanning/result views
    if (el.heroBrandCard) el.heroBrandCard.style.display = 'block';
    el.flipCardOuter.style.display = 'none';
    el.flipCardInner.classList.remove('flipped');
    el.scanningContainer.style.display = 'none';

    // 11) Render banner stats for active brand
    renderBannerStats();
  };

  // ── Render Brand Stats Pill ──────────────────────────────────────────────────
  function renderBannerStats() {
    if (!el.bannerStatsPills) return;
    const stats = state.stats || {};
    const activeKey = state.activeBrand || 'zomato';
    const brand = BRANDS[activeKey] || { name: activeKey };
    const pchecks = Number((stats.platform_checks && stats.platform_checks[activeKey]) || 0);
    const brandLabel = pchecks >= 1000 ? Math.floor(pchecks / 1000) + 'K+' : String(pchecks);

    el.bannerStatsPills.innerHTML = `
      <div class="banner-pill brand-stat-pill" title="${brand.name} platform total checks">
        <span>✓</span><span id="bannerPlatformTotal">${brand.name}: ${brandLabel}</span>
      </div>
    `;
  }

  window.switchBrandFromEngine = function (brandKey) {
    const chipEl = document.querySelector(`.service-chip[data-platform="${brandKey}"]`);
    switchBrand(brandKey, chipEl);
    // Switch to single tab
    switchTab('single');
    // Scroll chip into view
    if (chipEl) chipEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  };

  // ── Tab Navigation ───────────────────────────────────────────────────────────
  function switchTab(tabName) {
    state.currentTab = tabName;

    el.tabContents.forEach(tc => tc.classList.remove('active'));
    const target = document.getElementById('content' + tabName.charAt(0).toUpperCase() + tabName.slice(1));
    if (target) target.classList.add('active');

    el.modeTabs.forEach(t => {
      t.classList.toggle('active', t.dataset.tab === tabName);
    });

    el.bottomNavItems.forEach(b => {
      b.classList.toggle('active', b.dataset.tab === tabName);
    });

    if (tabName === 'history') renderHistory();
    haptic('selection');
  }

  // Tab click handlers
  el.modeTabs.forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));
  el.bottomNavItems.forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));

  // Direct URL hash navigation support (#history, #batch, #home)
  function handleUrlHash() {
    const rawHash = (window.location.hash || '').replace('#', '').toLowerCase();
    if (!rawHash) return;
    const tabMap = { history: 'history', batch: 'batch', home: 'single', single: 'single' };
    if (tabMap[rawHash]) {
      switchTab(tabMap[rawHash]);
    }
  }
  window.addEventListener('hashchange', handleUrlHash);
  setTimeout(handleUrlHash, 50);

  // ── Phone Input: Auto-format ─────────────────────────────────────────────────
  function cleanIndianPhone(val) {
    let raw = String(val || '').replace(/\D/g, '');
    if (raw.startsWith('91') && raw.length >= 11) {
      raw = raw.slice(2);
    }
    return raw.slice(0, 10);
  }

  el.mobileInput.addEventListener('input', (e) => {
    let raw = cleanIndianPhone(e.target.value);
    // Format: "98765 43210"
    if (raw.length > 5) {
      e.target.value = raw.slice(0, 5) + ' ' + raw.slice(5);
    } else {
      e.target.value = raw;
    }
    clearError();
  });

  el.mobileInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); doCheck(); }
  });

  // Paste & Clear
  el.btnPaste.addEventListener('click', async () => {
    try {
      const t = await navigator.clipboard.readText();
      const digits = cleanIndianPhone(t);
      el.mobileInput.value = digits.length > 5 ? digits.slice(0, 5) + ' ' + digits.slice(5) : digits;
      clearError();
      haptic('selection');
    } catch (e) { el.mobileInput.focus(); }
  });

  el.btnClear.addEventListener('click', () => {
    el.mobileInput.value = '';
    clearError();
    if (el.heroBrandCard) el.heroBrandCard.style.display = 'block';
    el.flipCardOuter.style.display = 'none';
    el.flipCardInner.classList.remove('flipped');
    haptic('selection');
  });

  // Demo buttons
  el.btnDemoRegistered.addEventListener('click', () => {
    const brand = BRANDS[state.activeBrand];
    const n = brand.demoRegistered;
    el.mobileInput.value = n.length > 5 ? n.slice(0,5) + ' ' + n.slice(5) : n;
    clearError();
    haptic('selection');
  });

  el.btnDemoFresh.addEventListener('click', () => {
    const brand = BRANDS[state.activeBrand];
    const n = brand.demoFresh;
    el.mobileInput.value = n.length > 5 ? n.slice(0,5) + ' ' + n.slice(5) : n;
    clearError();
    haptic('selection');
  });

  // ── CTA Button: Spring Bounce ────────────────────────────────────────────────
  el.btnCheck.addEventListener('click', () => {
    el.btnCheck.classList.add('spring-bounce');
    el.btnCheck.addEventListener('animationend', () => el.btnCheck.classList.remove('spring-bounce'), { once: true });
    doCheck();
  });

  // Re-check
  el.btnRecheck.addEventListener('click', () => {
    if (el.heroBrandCard) el.heroBrandCard.style.display = 'block';
    el.flipCardOuter.style.display = 'none';
    el.flipCardInner.classList.remove('flipped');
    el.mobileInput.value = '';
    el.mobileInput.focus();
    haptic('selection');
  });

  // ── Phone Validation ─────────────────────────────────────────────────────────
  function getCleanPhone() {
    return cleanIndianPhone(el.mobileInput.value);
  }

  function validatePhone(phone) {
    if (phone.length !== 10) return 'Enter a valid 10-digit mobile number';
    if (!/^[6-9]/.test(phone)) return 'Indian numbers must start with 6-9';
    return null;
  }

  function showError(msg) {
    el.errorBanner.textContent = msg;
    el.errorBanner.style.display = 'block';
  }

  function clearError() {
    el.errorBanner.style.display = 'none';
    el.errorBanner.textContent = '';
  }

  // ── Keyboard Dismiss (iOS) ───────────────────────────────────────────────────
  function dismissKeyboard() {
    el.mobileInput.blur();
    document.activeElement?.blur?.();
  }

  // ── Haptic Feedback ─────────────────────────────────────────────────────────
  function haptic(type) {
    try {
      if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast('6.1') && tg.HapticFeedback) {
        if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
        else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
        else if (type === 'selection') tg.HapticFeedback.selectionChanged();
        else if (type === 'impact') tg.HapticFeedback.impactOccurred('medium');
      } else if (navigator.vibrate) {
        if (type === 'success') navigator.vibrate([30, 30, 30]);
        else if (type === 'error') navigator.vibrate([80, 30, 80]);
        else if (type === 'impact') navigator.vibrate(40);
        else navigator.vibrate(20);
      }
    } catch { /* non-blocking */ }
  }

  // ── Sound Cue ─────────────────────────────────────────────────────────────────
  function playSound(type) {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      gain.gain.setValueAtTime(0.15, ctx.currentTime);

      if (type === 'success') {
        osc.frequency.setValueAtTime(880, ctx.currentTime);
        osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.1);
      } else if (type === 'beep') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(660, ctx.currentTime);
      } else if (type === 'error') {
        osc.frequency.setValueAtTime(300, ctx.currentTime);
      }

      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.3);
    } catch { /* non-blocking */ }
  }

  // ── Confetti Burst ────────────────────────────────────────────────────────────
  function launchConfetti() {
    const canvas = el.confettiCanvas;
    const ctx = canvas.getContext('2d');
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
    canvas.style.display = 'block';

    const brand = BRANDS[state.activeBrand];
    const colors = [brand.primary, '#fff', '#4ade80', '#fbbf24', '#f472b6', '#38bdf8'];

    const particles = Array.from({ length: 100 }, () => ({
      x: Math.random() * canvas.width,
      y: -10,
      r: Math.random() * 6 + 3,
      d: Math.random() * 100,
      color: colors[Math.floor(Math.random() * colors.length)],
      tilt: Math.random() * 20 - 10,
      tiltAngle: 0,
      tiltAngleIncrement: (Math.random() * 0.07 + 0.05),
      vy: Math.random() * 3 + 1,
      vx: Math.random() * 4 - 2,
    }));

    let frame;
    let elapsed = 0;

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => {
        ctx.beginPath();
        ctx.fillStyle = p.color;
        ctx.ellipse(p.x, p.y, p.r, p.r * 0.6, p.tiltAngle, 0, 2 * Math.PI);
        ctx.fill();

        p.tiltAngle += p.tiltAngleIncrement;
        p.y += p.vy;
        p.x += p.vx;
        p.vy += 0.05; // gravity
      });

      elapsed++;
      if (elapsed < 150 && particles.some(p => p.y < canvas.height)) {
        frame = requestAnimationFrame(draw);
      } else {
        cancelAnimationFrame(frame);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        canvas.style.display = 'none';
      }
    }

    draw();
  }

  // ── Copy to Clipboard Toast ───────────────────────────────────────────────────
  function copyToClipboard(text) {
    try {
      navigator.clipboard.writeText(text).then(() => showCopyToast('📋 Copied!'));
    } catch {
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0;';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showCopyToast('📋 Copied!');
    }
    haptic('selection');
  }

  function showCopyToast(msg) {
    el.copyToast.textContent = msg;
    el.copyToast.classList.add('visible');
    setTimeout(() => el.copyToast.classList.remove('visible'), 2000);
  }

  el.resultPhoneTap.addEventListener('click', () => {
    copyToClipboard(getResultPhone());
  });

  let _resultPhoneRaw = '';
  function getResultPhone() { return _resultPhoneRaw; }

  // ── Scanning Steps Animation ──────────────────────────────────────────────────
  function animateScanSteps(steps, duration) {
    const stepDuration = Math.floor(duration / (steps.length + 1));
    steps.forEach((step, i) => {
      setTimeout(() => {
        el.scanStepText.textContent = step;
        el.scanStepDetail.textContent = `Step ${i + 1} of ${steps.length}`;
      }, stepDuration * i);
    });
  }

  // ── Main Check Function ───────────────────────────────────────────────────────
  function doCheck() {
    const phone = getCleanPhone();
    const err = validatePhone(phone);
    if (err) { showError(err); haptic('error'); return; }

    clearError();
    dismissKeyboard();

    const brand = BRANDS[state.activeBrand];
    state.checkStartTime = Date.now();

    // Show scanning
    el.heroBrandCard && (el.heroBrandCard = document.getElementById('heroBrandCard'));
    document.getElementById('heroBrandCard').style.display = 'none';
    el.flipCardOuter.style.display = 'none';
    el.flipCardInner.classList.remove('flipped');
    el.scanningContainer.style.display = 'flex';

    // Scan emoji
    const scanUrl = fluentUrl(brand.scanEmoji);
    if (scanUrl) el.scanEmojiImg.src = scanUrl;

    // Animate steps
    animateScanSteps(brand.scanSteps, 2400);

    // Disable btn
    el.btnCheck.disabled = true;
    el.ctaSpinner.style.display = 'block';
    el.ctaLabel.textContent = 'Checking...';

    haptic('impact');
    playSound('beep');

    // API call
    callCheckAPI(phone, state.activeBrand)
      .then(result => renderResult(phone, result, brand))
      .catch(err => {
        el.scanningContainer.style.display = 'none';
        document.getElementById('heroBrandCard').style.display = 'block';
        showError(err.message || 'Check failed. Try again.');
        haptic('error');
        playSound('error');
      })
      .finally(() => {
        el.btnCheck.disabled = false;
        el.ctaSpinner.style.display = 'none';
        el.ctaLabel.textContent = brand.ctaLabel;
      });
  }

  // ── API Call ──────────────────────────────────────────────────────────────────
  async function callCheckAPI(phone, platform) {
    const resp = await apiFetch('/api/checker/phone', {
      method: 'POST',
      body: JSON.stringify({ phone, platform }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
  }

  // ── Render Result ─────────────────────────────────────────────────────────────
  function renderResult(phone, result, brand) {
    const elapsed = Date.now() - state.checkStartTime;

    // ── ERROR / CHALLENGE state: checker engine offline / challenge / API error ──
    if (result.status === 'ERROR' || result.status === 'CHALLENGE' || (!result.success && result.status !== 'NOT_REGISTERED' && result.status !== 'REGISTERED')) {
      el.scanningContainer.style.display = 'none';
      el.flipCardOuter.style.display = 'none';
      document.getElementById('heroBrandCard').style.display = 'block';
      let errMsg = result.error || result.detail;
      if (result.status === 'CHALLENGE') {
        errMsg = `${brand.name} anti-bot challenge active. Server IP rate-limited or in maintenance mode.`;
      }
      showError('⚠ ' + (errMsg || 'Checker engine unavailable. Try again later.'));
      haptic('error');
      return;
    }

    // Update real-time stats immediately
    if (result.universal_total_checks != null) {
      state.stats.total_checks = result.universal_total_checks;
    } else {
      state.stats.total_checks = (state.stats.total_checks || 0) + 1;
    }
    state.stats.platform_checks = state.stats.platform_checks || {};
    if (result.platform_total_checks != null) {
      state.stats.platform_checks[state.activeBrand] = result.platform_total_checks;
    } else {
      state.stats.platform_checks[state.activeBrand] = (state.stats.platform_checks[state.activeBrand] || 0) + 1;
    }
    renderBannerStats();

    const isRegistered = result.registered === true;
    const isFresh      = result.fresh === true || result.registered === false;

    _resultPhoneRaw = '+91 ' + phone.slice(0,5) + ' ' + phone.slice(5);

    // Result fields
    if (el.resultBrandLogo) {
      el.resultBrandLogo.src = brand.logo;
      el.resultBrandLogo.alt = brand.name;
    }
    el.resultBrandName.textContent = brand.name.toUpperCase();
    el.resPlatformVal.textContent  = brand.name;
    el.resStatusVal.textContent    = isFresh ? 'Fresh (Available)' : 'Already Registered';
    el.resStatusVal.className      = 'meta-value ' + (isFresh ? 'fresh' : 'taken');
    el.resFreshVal.textContent     = isFresh ? 'Fresh / Unused' : 'Existing Account';
    el.resFreshVal.className       = 'meta-value ' + (isFresh ? 'fresh' : 'taken');
    el.resTimeVal.textContent      = elapsed + 'ms';
    el.resultPhoneNum.textContent  = _resultPhoneRaw;

    // Reversed narrative: Fresh number is WIN (positive green), Registered is TAKEN (neutral/taken)
    if (isFresh) {
      el.verdictTitle.textContent    = 'Fresh Number ✓';
      el.verdictTitle.className      = 'verdict-title fresh';
      el.verdictSubtitle.textContent = brand.resultDescriptions?.fresh || 'Number is fresh and available for new account registration.';
      if (el.resultStatusBadge) {
        el.resultStatusBadge.className = 'result-status-badge fresh';
      }
      el.resultStatusIcon.textContent = '●';
      el.resultStatusText.textContent = 'FRESH / AVAILABLE';
    } else {
      el.verdictTitle.textContent    = 'Already Registered';
      el.verdictTitle.className      = 'verdict-title taken';
      el.verdictSubtitle.textContent = brand.resultDescriptions?.registered || ('Account already exists on ' + brand.name);
      if (el.resultStatusBadge) {
        el.resultStatusBadge.className = 'result-status-badge taken';
      }
      el.resultStatusIcon.textContent = '○';
      el.resultStatusText.textContent = 'ALREADY REGISTERED';
    }

    // Service brand logo inside verdict icon container instead of emoji
    if (el.verdictEmojiImg) {
      el.verdictEmojiImg.src = brand.logo;
      el.verdictEmojiImg.alt = brand.name;
      el.verdictEmojiImg.style.display = 'block';
    }
    if (el.verdictEmojiFallback) {
      el.verdictEmojiFallback.style.display = 'none';
    }

    // Hide scanning, show result card directly
    el.scanningContainer.style.display = 'none';
    el.flipCardOuter.style.display = 'block';

    // Trigger reveal effects: celebration for FRESH (available), subtle for registered
    if (isFresh) {
      launchConfetti();
      haptic('success');
      playSound('success');
    } else {
      haptic('impact');
    }

    // Save to history
    saveHistory({ phone, platform: state.activeBrand, brandName: brand.name, registered: isRegistered, fresh: isFresh, time: Date.now() });
  }

  // ── High-Class Server-Side History ──────────────────────────────────────────
  let historyFetching = false;

  async function fetchServerHistory() {
    if (historyFetching) return;
    historyFetching = true;
    try {
      const resp = await apiFetch('/api/history?limit=50');
      if (resp.ok) {
        const data = await resp.json();
        if (data && Array.isArray(data.history)) {
          state.history = data.history;
          localStorage.setItem('nex_checker_history', JSON.stringify(data.history.slice(0, 25)));
        }
      }
    } catch (err) {
      console.warn('Could not load server history:', err);
    } finally {
      historyFetching = false;
      renderHistoryUI();
    }
  }

  function saveHistory(entry) {
    state.history.unshift(entry);
    if (state.history.length > 50) state.history = state.history.slice(0, 50);
    localStorage.setItem('nex_checker_history', JSON.stringify(state.history));
    renderHistoryUI();
    // Synchronize authoritative server history shortly after API completes
    setTimeout(fetchServerHistory, 400);
  }

  function renderHistory() {
    renderHistoryUI();
    fetchServerHistory();
  }

  function renderHistoryUI() {
    const list = el.historyList;
    if (!list) return;
    list.innerHTML = '';

    if (!state.history || !state.history.length) {
      list.innerHTML = `
        <div class="history-empty">
          <div class="empty-emoji">📭</div>
          <div class="empty-title">No checks yet</div>
          <div class="empty-sub">Run a check on the Home tab to log history</div>
        </div>`;
      return;
    }

    state.history.forEach((entry, idx) => {
      const item = document.createElement('div');
      item.className = 'history-item';
      item.dataset.idx = idx;
      if (entry.id) item.dataset.id = entry.id;

      const pKey = (entry.platform || 'zomato').toLowerCase();
      const brandCfg = BRANDS[pKey] || {};
      const dotColor = brandCfg.primary || '#E23744';

      const entryTime = entry.timestamp ? (entry.timestamp * 1000) : (entry.time || Date.now());
      const timeStr  = new Date(entryTime).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
      const dateStr  = new Date(entryTime).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

      const rawPhone = String(entry.phone || '');
      const formatted = rawPhone.length === 10 ? rawPhone.replace(/(\d{5})(\d{5})/, '$1 $2') : rawPhone;

      const isFresh = entry.fresh === true || entry.registered === false;

      item.innerHTML = `
        <div class="hist-brand-dot" style="background:${dotColor};"></div>
        <div class="hist-phone">+91 ${formatted}</div>
        <div class="hist-meta">
          <span class="hist-status ${isFresh ? 'fresh' : 'registered'}">${isFresh ? '✓ Fresh' : '● Registered'}</span>
          <span class="hist-platform">${entry.brand_name || entry.brandName || brandCfg.name || pKey}</span>
          <span class="hist-time">${dateStr}, ${timeStr}</span>
        </div>`;

      // Long press to delete
      let pressTimer;
      item.addEventListener('pointerdown', () => {
        pressTimer = setTimeout(() => {
          item.classList.add('shaking');
          haptic('impact');
          setTimeout(() => {
            item.classList.remove('shaking');
            if (confirm(`Delete check history for +91 ${formatted}?`)) {
              item.classList.add('deleting');
              setTimeout(async () => {
                if (entry.id) {
                  try {
                    await apiFetch(`/api/history/${entry.id}`, { method: 'DELETE' });
                  } catch (e) {}
                }
                state.history = state.history.filter((_, i) => i !== idx);
                localStorage.setItem('nex_checker_history', JSON.stringify(state.history));
                renderHistoryUI();
              }, 300);
            }
          }, 400);
        }, 600);
      });
      item.addEventListener('pointerup', () => clearTimeout(pressTimer));
      item.addEventListener('pointercancel', () => clearTimeout(pressTimer));

      list.appendChild(item);
    });
  }

  el.btnHistoryClear.addEventListener('click', async () => {
    if (!state.history.length) return;
    if (confirm('Clear all check history from server?')) {
      haptic('selection');
      try {
        await apiFetch('/api/history/clear', { method: 'POST' });
      } catch (err) {
        console.warn('Server history clear failed:', err);
      }
      state.history = [];
      localStorage.removeItem('nex_checker_history');
      renderHistoryUI();
    }
  });

  // Pull-to-refresh on history
  (function setupPTR() {
    const histSection = document.getElementById('contentHistory');
    let startY = 0;
    let pulling = false;

    histSection.addEventListener('touchstart', e => {
      if (histSection.scrollTop === 0) { startY = e.touches[0].clientY; pulling = true; }
    }, { passive: true });

    histSection.addEventListener('touchmove', e => {
      if (!pulling) return;
      const dy = e.touches[0].clientY - startY;
      if (dy > 50) el.ptrIndicator.classList.add('visible');
    }, { passive: true });

    histSection.addEventListener('touchend', () => {
      if (el.ptrIndicator.classList.contains('visible')) {
        setTimeout(() => {
          el.ptrIndicator.classList.remove('visible');
          renderHistory();
          haptic('selection');
        }, 800);
      }
      pulling = false;
    });
  })();

  // ── Batch Check ───────────────────────────────────────────────────────────────
  el.btnBatchPaste.addEventListener('click', async () => {
    try {
      const t = await navigator.clipboard.readText();
      el.batchInput.value = t;
    } catch { el.batchInput.focus(); }
  });

  el.btnBatchClear.addEventListener('click', () => {
    el.batchInput.value = '';
    el.batchResults.innerHTML = '';
    el.batchExportRow.style.display = 'none';
    el.batchProgress.style.display = 'none';
  });

  el.btnBatchRun.addEventListener('click', runBatch);

  async function runBatch() {
    if (state.batchRunning) return;
    const brand = BRANDS[state.activeBrand];

    const raw = el.batchInput.value;
    const phones = raw.split(/[\n,;\s]+/)
      .map(p => p.replace(/\D/g, ''))
      .filter(p => p.length === 10 && /^[6-9]/.test(p))
      .slice(0, 50);

    if (!phones.length) { showCopyToast('⚠ No valid numbers found'); return; }

    state.batchRunning = true;
    state.batchResults = [];
    el.batchResults.innerHTML = '';
    el.batchExportRow.style.display = 'none';
    el.batchProgress.style.display = 'block';

    haptic('impact');

    for (let i = 0; i < phones.length; i++) {
      const phone = phones[i];
      el.batchProgressText.textContent = `Checking ${i + 1} / ${phones.length}`;
      el.batchProgressFill.style.width = ((i + 1) / phones.length * 100) + '%';

      // Add pending row
      const row = createBatchRow(phone, 'checking');
      el.batchResults.appendChild(row);

      try {
        const result = await callCheckAPI(phone, state.activeBrand);
        const isReg = result.registered === true;
        const isFresh = result.fresh === true || result.registered === false;
        row.querySelector('.batch-status-dot').className = `batch-status-dot ${isFresh ? 'fresh' : 'registered'}`;
        row.querySelector('.batch-status-label').className = `batch-status-label ${isFresh ? 'fresh' : 'registered'}`;
        row.querySelector('.batch-status-label').textContent = isFresh ? '✓ Fresh' : '● Registered';
        state.batchResults.push({ phone, platform: state.activeBrand, brandName: brand.name, registered: isReg, fresh: isFresh });
        if (isFresh) haptic('success');
      } catch {
        row.querySelector('.batch-status-dot').className = 'batch-status-dot taken';
        row.querySelector('.batch-status-label').textContent = '⚠ Error';
        state.batchResults.push({ phone, platform: state.activeBrand, brandName: brand.name, registered: null, fresh: null });
      }

      // Small delay between requests
      if (i < phones.length - 1) await sleep(400);
    }

    state.batchRunning = false;
    el.batchProgressText.textContent = `Done — ${phones.length} numbers checked`;
    el.batchExportRow.style.display = 'block';
    haptic('success');
    playSound('success');
  }

  function createBatchRow(phone, status) {
    const row = document.createElement('div');
    row.className = 'batch-result-row';
    row.innerHTML = `
      <div class="batch-status-dot ${status}"></div>
      <div class="batch-result-phone">+91 ${phone.slice(0,5)} ${phone.slice(5)}</div>
      <div class="batch-status-label" style="color:var(--text-muted);">Checking...</div>`;
    return row;
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  // Export CSV
  el.btnBatchExport.addEventListener('click', () => {
    const csv = ['Phone,Platform,Status']
      .concat(state.batchResults.map(r =>
        `"+91${r.phone}","${r.brandName}","${r.registered === true ? 'Registered' : r.registered === false ? 'Not Found' : 'Error'}"`
      )).join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `nexchecker_${state.activeBrand}_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showCopyToast('📥 CSV downloaded!');
  });

  // ── API Health Check + Real Stats ────────────────────────────────────────────
  async function checkHealth() {
    try {
      const r = await fetch('/api/health');
      if (!r.ok) throw new Error();
      const data = await r.json();
      // Update live indicator
      const pulse = document.querySelector('.status-pulse');
      const text  = document.querySelector('.status-text');
      if (pulse) pulse.style.background = '';
      if (text)  { text.textContent = 'LIVE'; text.style.color = ''; }
      // Render real stats if available
      if (data) {
        state.stats = {
          total_checks: data.total_checks || 0,
          registered_checks: data.registered_checks || 0,
          fresh_checks: data.fresh_checks || 0,
          platform_checks: data.platform_checks || {},
        };
        renderBannerStats();
      }
    } catch {
      const pulse = document.querySelector('.status-pulse');
      const text  = document.querySelector('.status-text');
      if (pulse) pulse.style.background = '#f87171';
      if (text)  { text.textContent = 'DOWN'; text.style.color = '#f87171'; }
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────────
  async function init() {
    // 1) Enforce strict Telegram cryptographic authentication before doing anything
    const isAuthed = await enforceTelegramSecurity();
    if (!isAuthed) {
      console.warn('[NexChecker Security] Direct browser access locked. Awaiting verified Telegram WebApp session.');
      return;
    }

    // Apply default brand
    switchBrand('zomato', document.querySelector('.service-chip[data-platform="zomato"]'));

    // Handle URL search parameters (e.g. ?phone=9027936246&platform=zomato)
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const qPlatform = (urlParams.get('platform') || '').toLowerCase();
      const qPhone = urlParams.get('phone');
      if (qPlatform && BRANDS[qPlatform]) {
        const chip = document.querySelector(`.service-chip[data-platform="${qPlatform}"]`);
        switchBrand(qPlatform, chip);
      }
      if (qPhone) {
        const clean = cleanIndianPhone(qPhone);
        if (clean) {
          el.mobileInput.value = clean.length > 5 ? clean.slice(0, 5) + ' ' + clean.slice(5) : clean;
          if (clean.length === 10) {
            setTimeout(() => doCheck(), 350);
          }
        }
      }
    } catch (_) {}

    // Health check every 30s
    checkHealth();
    setInterval(checkHealth, 30000);

    // Render history
    renderHistory();

    // Focus input if not pre-filled
    if (!el.mobileInput.value) {
      setTimeout(() => el.mobileInput.focus(), 300);
    }

    // Ensure confetti canvas hidden by default
    el.confettiCanvas.style.display = 'none';
  }

  init();

})();
