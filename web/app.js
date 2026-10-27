/**
 * Zomato Checker — Web Application Client Logic
 * Handles interactive verification, batch operations, history, and Telegram WebApp integration.
 */

(function () {
  'use strict';

  // ── Telegram WebApp Initialization ─────────────────────────────────────────
  const tg = window.Telegram?.WebApp;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.enableClosingConfirmation) tg.enableClosingConfirmation();
    } catch (e) {
      console.warn('Telegram WebApp init warning:', e);
    }
  }

  // ── State Management ───────────────────────────────────────────────────────
  const state = {
    selectedPlatform: 'zomato',
    currentTab: 'single',
    history: JSON.parse(localStorage.getItem('nex_zomato_history') || '[]'),
    batchResults: [],
  };

  // ── DOM Element Cache ──────────────────────────────────────────────────────
  const el = {
    // Tabs & Nav
    modeTabs: document.querySelectorAll('.mode-tab'),
    bottomNavItems: document.querySelectorAll('.b-nav-item'),
    tabContents: document.querySelectorAll('.tab-content'),
    
    // Platform Chips
    platformChips: document.querySelectorAll('.platform-chip'),

    // Single Check Elements
    mobileInput: document.getElementById('mobileInput'),
    btnCheck: document.getElementById('btnCheck'),
    ctaLabel: document.getElementById('ctaLabel'),
    ctaSpinner: document.getElementById('ctaSpinner'),
    btnPaste: document.getElementById('btnPaste'),
    btnClear: document.getElementById('btnClear'),
    btnDemoRegistered: document.getElementById('btnDemoRegistered'),
    btnDemoFresh: document.getElementById('btnDemoFresh'),
    errorBanner: document.getElementById('errorBanner'),
    scanningContainer: document.getElementById('scanningContainer'),
    scanStepText: document.getElementById('scanStepText'),
    resultCard: document.getElementById('resultCard'),

    // Result Fields
    resultDietIndicator: document.getElementById('resultDietIndicator'),
    resultVerdictTitle: document.getElementById('resultVerdictTitle'),
    resultVerdictSubtitle: document.getElementById('resultVerdictSubtitle'),
    resultStatusBadge: document.getElementById('resultStatusBadge'),
    resultPhoneHighlight: document.getElementById('resultPhoneHighlight'),
    resPlatformVal: document.getElementById('resPlatformVal'),
    resStatusVal: document.getElementById('resStatusVal'),
    resOtpVal: document.getElementById('resOtpVal'),
    resLatencyVal: document.getElementById('resLatencyVal'),
    resultAdviceBox: document.getElementById('resultAdviceBox'),
    adviceIcon: document.getElementById('adviceIcon'),
    adviceContent: document.getElementById('adviceContent'),
    multiPlatformGrid: document.getElementById('multiPlatformGrid'),
    multiGridItems: document.getElementById('multiGridItems'),
    btnCopyResult: document.getElementById('btnCopyResult'),
    btnShareTelegram: document.getElementById('btnShareTelegram'),

    // Batch Elements
    batchInput: document.getElementById('batchInput'),
    btnPasteBatch: document.getElementById('btnPasteBatch'),
    btnClearBatch: document.getElementById('btnClearBatch'),
    batchCounter: document.getElementById('batchCounter'),
    btnStartBatch: document.getElementById('btnStartBatch'),
    batchProgressBox: document.getElementById('batchProgressBox'),
    batchProgressFill: document.getElementById('batchProgressFill'),
    batchProgressPercent: document.getElementById('batchProgressPercent'),
    batchSummaryPanel: document.getElementById('batchSummaryPanel'),
    batchTotalCount: document.getElementById('batchTotalCount'),
    batchFreshCount: document.getElementById('batchFreshCount'),
    batchRegCount: document.getElementById('batchRegCount'),
    batchErrCount: document.getElementById('batchErrCount'),
    batchFilterChips: document.querySelectorAll('.filter-chip'),
    fAllCount: document.getElementById('fAllCount'),
    fFreshCount: document.getElementById('fFreshCount'),
    fRegCount: document.getElementById('fRegCount'),
    batchResultsList: document.getElementById('batchResultsList'),
    btnCopyFreshList: document.getElementById('btnCopyFreshList'),
    btnExportCsv: document.getElementById('btnExportCsv'),

    // History Elements
    historyList: document.getElementById('historyList'),
    btnClearHistory: document.getElementById('btnClearHistory'),

    // Toast Container
    toastContainer: document.getElementById('toastContainer'),
  };

  // ── Helper Utilities ───────────────────────────────────────────────────────
  function showToast(msg, duration = 2500) {
    const toast = document.createElement('div');
    toast.className = 'toast-msg';
    toast.textContent = msg;
    el.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      setTimeout(() => toast.remove(), 200);
    }, duration);
  }

  function cleanPhone(val) {
    if (!val) return '';
    const digits = val.replace(/\D/g, '');
    if (digits.length >= 10) return digits.slice(-10);
    return digits;
  }

  function formatPhoneDisplay(num) {
    const p = cleanPhone(num);
    if (p.length === 10) {
      return `+91 ${p.slice(0, 5)} ${p.slice(5)}`;
    }
    return `+91 ${p}`;
  }

  function triggerHaptic(type = 'impact') {
    if (tg?.HapticFeedback) {
      try {
        if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
        else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
        else tg.HapticFeedback.impactOccurred('medium');
      } catch (e) {}
    }
  }

  // ── Tab Navigation ─────────────────────────────────────────────────────────
  function switchTab(tabId) {
    state.currentTab = tabId;
    el.modeTabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
    el.bottomNavItems.forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
    el.tabContents.forEach(c => {
      c.style.display = c.id === `content${capitalize(tabId)}` ? 'block' : 'none';
    });
    if (tabId === 'history') renderHistory();
  }

  function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  el.modeTabs.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
  el.bottomNavItems.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));

  // ── Platform Selection Carousel ────────────────────────────────────────────
  el.platformChips.forEach(chip => {
    chip.addEventListener('click', () => {
      el.platformChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.selectedPlatform = chip.dataset.platform;
      triggerHaptic('impact');
      showToast(`Selected Engine: ${chip.querySelector('.p-name').textContent}`);
    });
  });

  // ── Input Helpers ──────────────────────────────────────────────────────────
  el.mobileInput.addEventListener('input', (e) => {
    const raw = e.target.value.replace(/\D/g, '');
    e.target.value = raw.slice(0, 10);
    el.errorBanner.style.display = 'none';
  });

  el.btnPaste.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      const cleaned = cleanPhone(text);
      if (cleaned) {
        el.mobileInput.value = cleaned;
        showToast('📋 Phone number pasted');
        triggerHaptic('impact');
      } else {
        showToast('⚠️ No valid 10-digit number in clipboard');
      }
    } catch {
      showToast('⚠️ Clipboard permission required');
    }
  });

  el.btnClear.addEventListener('click', () => {
    el.mobileInput.value = '';
    el.resultCard.style.display = 'none';
    el.errorBanner.style.display = 'none';
    el.mobileInput.focus();
  });

  el.btnDemoRegistered.addEventListener('click', () => {
    el.mobileInput.value = '7631328516';
    checkSingle('7631328516');
  });

  el.btnDemoFresh.addEventListener('click', () => {
    el.mobileInput.value = '7005999888';
    checkSingle('7005999888');
  });

  // ── Single Check Execution ─────────────────────────────────────────────────
  async function checkSingle(targetPhone = null) {
    const phone = cleanPhone(targetPhone || el.mobileInput.value);
    if (phone.length !== 10 || !['6', '7', '8', '9'].includes(phone[0])) {
      el.errorBanner.textContent = 'Please enter a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9';
      el.errorBanner.style.display = 'block';
      triggerHaptic('error');
      return;
    }

    el.errorBanner.style.display = 'none';
    el.resultCard.style.display = 'none';
    el.scanningContainer.style.display = 'block';
    el.btnCheck.disabled = true;
    el.ctaSpinner.style.display = 'inline-block';
    el.ctaLabel.textContent = 'Verifying...';

    const scanSteps = [
      `Connecting to ${capitalize(state.selectedPlatform)} engine...`,
      'Validating 0-OTP handshake...',
      'Synchronizing authoritative verdict...',
    ];
    let stepIdx = 0;
    const stepInterval = setInterval(() => {
      stepIdx = (stepIdx + 1) % scanSteps.length;
      el.scanStepText.textContent = scanSteps[stepIdx];
    }, 380);

    const startTime = performance.now();

    try {
      const response = await fetch('/api/checker/phone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_phone: phone,
          platform: state.selectedPlatform,
        }),
      });

      clearInterval(stepInterval);
      const latency = Math.round(performance.now() - startTime);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Server returned an error');
      }

      displaySingleResult(phone, data, latency);
      saveHistory(phone, data, latency);
      triggerHaptic('success');
    } catch (err) {
      clearInterval(stepInterval);
      el.errorBanner.textContent = `Verification Error: ${err.message}`;
      el.errorBanner.style.display = 'block';
      triggerHaptic('error');
    } finally {
      el.scanningContainer.style.display = 'none';
      el.btnCheck.disabled = false;
      el.ctaSpinner.style.display = 'none';
      el.ctaLabel.textContent = 'Check Registration • Free';
    }
  }

  el.btnCheck.addEventListener('click', () => checkSingle());
  el.mobileInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') checkSingle();
  });

  // ── Render Single Result ───────────────────────────────────────────────────
  function displaySingleResult(phone, data, latency) {
    const isRegistered = data.status === 'REGISTERED' || data.registered === true;
    const isAll = state.selectedPlatform === 'all' && data.platforms;

    el.resultCard.className = `result-card ${isRegistered ? 'verdict-registered' : 'verdict-fresh'}`;
    el.resultDietIndicator.className = `diet-indicator ${isRegistered ? 'non-veg' : 'veg'}`;
    el.resultVerdictTitle.textContent = isRegistered ? 'ACCOUNT FOUND 🎯' : '100% FRESH NUMBER ✅';
    el.resultVerdictSubtitle.textContent = isRegistered
      ? 'Existing registered customer detected'
      : '0 existing registrations detected';
    el.resultStatusBadge.textContent = isRegistered ? 'REGISTERED' : 'UNREGISTERED';
    el.resultPhoneHighlight.textContent = formatPhoneDisplay(phone);

    el.resPlatformVal.textContent = capitalize(state.selectedPlatform);
    el.resStatusVal.textContent = isRegistered ? 'Active User' : 'Available (Fresh)';
    el.resOtpVal.textContent = '0 (100% Silent)';
    el.resLatencyVal.textContent = `${latency}ms`;

    if (isRegistered) {
      el.adviceIcon.textContent = '🎯';
      el.adviceContent.textContent =
        'Active account on this platform. User already has profile history; not eligible for first-order coupons.';
    } else {
      el.adviceIcon.textContent = '✨';
      el.adviceContent.textContent =
        'Completely fresh number! 100% eligible for New User Discounts, Free Delivery, and Referral Bonuses.';
    }

    // Handle Multi-Platform Grid if 'all' was scanned
    if (isAll) {
      el.multiPlatformGrid.style.display = 'block';
      el.multiGridItems.innerHTML = '';
      Object.entries(data.platforms).forEach(([plat, res]) => {
        const reg = res.status === 'REGISTERED' || res.registered === true;
        const div = document.createElement('div');
        div.className = `multi-item ${reg ? 'is-reg' : 'is-fresh'}`;
        div.innerHTML = `
          <span class="multi-name">${capitalize(plat)}</span>
          <span class="multi-pill ${reg ? 'reg' : 'fresh'}">${reg ? 'REG' : 'FRESH'}</span>
        `;
        el.multiGridItems.appendChild(div);
      });
    } else {
      el.multiPlatformGrid.style.display = 'none';
    }

    el.resultCard.style.display = 'block';
    el.resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ── Copy & Share Handlers ──────────────────────────────────────────────────
  el.btnCopyResult.addEventListener('click', () => {
    const phone = el.resultPhoneHighlight.textContent;
    const title = el.resultVerdictTitle.textContent;
    const plat = el.resPlatformVal.textContent;
    const text = `Zomato Checker Result:\n📱 Number: ${phone}\n🛒 Platform: ${plat}\n🎯 Status: ${title}\n⚡ 0 OTP Sent | Authoritative Sync`;
    navigator.clipboard.writeText(text);
    showToast('📋 Result copied to clipboard!');
    triggerHaptic('impact');
  });

  el.btnShareTelegram.addEventListener('click', () => {
    const phone = el.resultPhoneHighlight.textContent;
    const title = el.resultVerdictTitle.textContent;
    const plat = el.resPlatformVal.textContent;
    const msg = encodeURIComponent(`🔍 Verification Report\n📱 ${phone}\n🛒 ${plat}\n🎯 ${title}`);
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(`https://t.me/share/url?url=${msg}`);
    } else {
      window.open(`https://t.me/share/url?url=${msg}`, '_blank');
    }
  });

  // ── Batch Check Execution ──────────────────────────────────────────────────
  function parseBatchPhones() {
    const raw = el.batchInput.value;
    const matches = raw.match(/\b\d{10}\b/g) || [];
    return Array.from(new Set(matches)).slice(0, 50);
  }

  el.batchInput.addEventListener('input', () => {
    const list = parseBatchPhones();
    el.batchCounter.textContent = `${list.length} valid numbers`;
  });

  el.btnPasteBatch.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      el.batchInput.value = text;
      const list = parseBatchPhones();
      el.batchCounter.textContent = `${list.length} valid numbers`;
      showToast(`📋 Pasted ${list.length} numbers`);
    } catch {
      showToast('⚠️ Unable to access clipboard');
    }
  });

  el.btnClearBatch.addEventListener('click', () => {
    el.batchInput.value = '';
    el.batchCounter.textContent = '0 numbers';
    el.batchSummaryPanel.style.display = 'none';
    el.batchProgressBox.style.display = 'none';
  });

  el.btnStartBatch.addEventListener('click', async () => {
    const phones = parseBatchPhones();
    if (phones.length === 0) {
      showToast('⚠️ Please enter at least 1 valid 10-digit number');
      return;
    }

    el.btnStartBatch.disabled = true;
    el.batchProgressBox.style.display = 'block';
    el.batchSummaryPanel.style.display = 'none';
    el.batchProgressFill.style.width = '20%';
    el.batchProgressPercent.textContent = '20%';

    try {
      const resp = await fetch('/api/checker/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phones: phones,
          platform: state.selectedPlatform,
        }),
      });

      el.batchProgressFill.style.width = '80%';
      el.batchProgressPercent.textContent = '80%';

      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Batch check failed');

      el.batchProgressFill.style.width = '100%';
      el.batchProgressPercent.textContent = '100%';

      state.batchResults = Object.entries(data.results || {}).map(([num, r]) => ({
        number: num,
        status: r.status,
        registered: r.status === 'REGISTERED' || r.registered === true,
        fresh: r.status === 'NOT_REGISTERED' || r.fresh === true,
      }));

      renderBatchResults('all');
      triggerHaptic('success');
    } catch (e) {
      showToast(`Batch Error: ${e.message}`);
      triggerHaptic('error');
    } finally {
      el.btnStartBatch.disabled = false;
      setTimeout(() => {
        el.batchProgressBox.style.display = 'none';
      }, 600);
    }
  });

  function renderBatchResults(filter = 'all') {
    const items = state.batchResults;
    const total = items.length;
    const fresh = items.filter(i => i.fresh).length;
    const reg = items.filter(i => i.registered).length;
    const err = items.filter(i => !i.fresh && !i.registered).length;

    el.batchTotalCount.textContent = total;
    el.batchFreshCount.textContent = fresh;
    el.batchRegCount.textContent = reg;
    el.batchErrCount.textContent = err;

    el.fAllCount.textContent = total;
    el.fFreshCount.textContent = fresh;
    el.fRegCount.textContent = reg;

    let filtered = items;
    if (filter === 'fresh') filtered = items.filter(i => i.fresh);
    if (filter === 'registered') filtered = items.filter(i => i.registered);

    el.batchResultsList.innerHTML = '';
    filtered.forEach(item => {
      const row = document.createElement('div');
      row.className = 'batch-row';
      const badgeCls = item.fresh ? 'fresh' : item.registered ? 'reg' : 'err';
      const badgeText = item.fresh ? 'FRESH' : item.registered ? 'REG' : 'ERR';
      row.innerHTML = `
        <span class="batch-phone">+91 ${item.number}</span>
        <span class="batch-badge ${badgeCls}">${badgeText}</span>
      `;
      el.batchResultsList.appendChild(row);
    });

    el.batchSummaryPanel.style.display = 'block';
  }

  el.batchFilterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      el.batchFilterChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      renderBatchResults(chip.dataset.filter);
    });
  });

  el.btnCopyFreshList.addEventListener('click', () => {
    const freshList = state.batchResults.filter(i => i.fresh).map(i => i.number).join('\n');
    if (!freshList) {
      showToast('⚠️ No fresh numbers found in batch');
      return;
    }
    navigator.clipboard.writeText(freshList);
    showToast('📋 Fresh numbers copied to clipboard!');
    triggerHaptic('impact');
  });

  el.btnExportCsv.addEventListener('click', () => {
    if (!state.batchResults.length) return;
    const csvContent = 'data:text/csv;charset=utf-8,Number,Status\n' +
      state.batchResults.map(i => `${i.number},${i.registered ? 'REGISTERED' : 'FRESH'}`).join('\n');
    const encoded = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encoded);
    link.setAttribute('download', `zomato_batch_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
  });

  // ── History Storage & Display ──────────────────────────────────────────────
  function saveHistory(phone, data, latency) {
    const isRegistered = data.status === 'REGISTERED' || data.registered === true;
    const item = {
      phone,
      platform: state.selectedPlatform,
      isRegistered,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      latency,
    };
    state.history.unshift(item);
    if (state.history.length > 30) state.history.pop();
    localStorage.setItem('nex_zomato_history', JSON.stringify(state.history));
  }

  function renderHistory() {
    el.historyList.innerHTML = '';
    if (!state.history.length) {
      el.historyList.innerHTML = `
        <div class="history-empty">
          <div class="empty-icon">📜</div>
          <div class="empty-title">No Scans Recorded Yet</div>
          <div class="empty-desc">Numbers you check will appear here for fast re-auditing.</div>
        </div>
      `;
      return;
    }

    state.history.forEach((h, idx) => {
      const item = document.createElement('div');
      item.className = 'history-item';
      const badgeClass = h.isRegistered ? 'reg' : 'fresh';
      const badgeText = h.isRegistered ? 'REG' : 'FRESH';
      item.innerHTML = `
        <div class="h-meta">
          <div class="diet-indicator ${h.isRegistered ? 'non-veg' : 'veg'}" style="transform: scale(0.8);"></div>
          <div>
            <div class="h-phone">+91 ${h.phone}</div>
            <div class="h-time">${capitalize(h.platform)} • ${h.time} (${h.latency || 150}ms)</div>
          </div>
        </div>
        <div class="h-actions">
          <span class="batch-badge ${badgeClass}">${badgeText}</span>
          <button class="text-btn" data-phone="${h.phone}" data-plat="${h.platform}">Re-Check</button>
        </div>
      `;
      item.querySelector('button').addEventListener('click', (e) => {
        el.mobileInput.value = e.target.dataset.phone;
        state.selectedPlatform = e.target.dataset.plat;
        el.platformChips.forEach(c => c.classList.toggle('active', c.dataset.platform === state.selectedPlatform));
        switchTab('single');
        checkSingle(e.target.dataset.phone);
      });
      el.historyList.appendChild(item);
    });
  }

  el.btnClearHistory.addEventListener('click', () => {
    state.history = [];
    localStorage.removeItem('nex_zomato_history');
    renderHistory();
    showToast('🗑️ History cleared');
  });

  // ── Init API Health Status Check ───────────────────────────────────────────
  async function checkEngineHealth() {
    try {
      const r = await fetch('/api/health');
      if (r.ok) {
        document.getElementById('engineStatus').innerHTML = `
          <span class="status-pulse"></span>
          <span class="status-text">ENGINES LIVE</span>
        `;
      }
    } catch {}
  }

  checkEngineHealth();
})();
