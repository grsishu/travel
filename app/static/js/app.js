// TravelPay Core PWA Application Logic
const APP_STATE = {
  token: localStorage.getItem('tp_token') || null,
  user: null,
  activeTab: 'home',
  qrScanner: null,
  activeQuote: null,
  quoteTimerInterval: null,
  quoteSecondsLeft: 0,
  deviceFingerprint: localStorage.getItem('tp_device_id') || ('DEV-' + Math.random().toString(36).substring(2, 10).toUpperCase()),
  inactivityTimer: null,
  isLocked: false,
  language: localStorage.getItem('tp_lang') || 'en'
};

localStorage.setItem('tp_device_id', APP_STATE.deviceFingerprint);

// Internationalization Dictionaries
const I18N = {
  en: {
    scan_pay: "Scan & Pay",
    scan_desc: "Scan PromptPay, QRIS, SGQR or any merchant QR",
    wallet_balance: "Wallet Balance (INR)",
    add_funds: "Add Money",
    convert: "Convert",
    recent_activity: "Recent Activity",
    settings: "Profile & Settings",
    home: "Home",
    wallet: "Wallet",
    history: "History",
    profile: "Profile"
  },
  hi: {
    scan_pay: "स्कैन और भुगतान करें",
    scan_desc: "प्रॉम्प्टपे, क्यूआरआईएस, एसजीक्यूआर या कोई भी विदेशी क्यूआर स्कैन करें",
    wallet_balance: "वॉलेट बैलेंस (INR)",
    add_funds: "पैसे जोड़ें",
    convert: "मुद्रा बदलें",
    recent_activity: "हाल की गतिविधियाँ",
    settings: "प्रोफ़ाइल और सेटिंग्स",
    home: "होम",
    wallet: "वॉलेट",
    history: "इतिहास",
    profile: "प्रोफ़ाइल"
  },
  ta: {
    scan_pay: "ஸ்கேன் செய்து பணம் செலுத்துக",
    scan_desc: "PromptPay, QRIS, SGQR வெளிநாட்டு வணிகர் QR ஸ்கேன் செய்யவும்",
    wallet_balance: "வாலட் இருப்பு (INR)",
    add_funds: "பணம் சேர்",
    convert: "நாணயம் மாற்று",
    recent_activity: "சமீபத்திய பரிவர்த்தனைகள்",
    settings: "சுயவிவரம் & அமைப்புகள்",
    home: "முகப்பு",
    wallet: "வாலட்",
    history: "வரலாறு",
    profile: "சுயவிவரம்"
  }
};

// --- INITIALIZATION ---
window.addEventListener('DOMContentLoaded', async () => {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(err => console.log('SW registration error:', err));
  }
  setupEventListeners();
  setupInactivityTracker();
  applyLanguage(APP_STATE.language);

  // Check login state
  if (APP_STATE.token) {
    await fetchUserProfile();
  } else {
    showView('view-welcome');
  }
});

// --- INACTIVITY 60S LOCK ---
function setupInactivityTracker() {
  let timeoutId;
  const resetTimer = () => {
    if (APP_STATE.isLocked || !APP_STATE.user || !APP_STATE.user.activation_step || APP_STATE.user.activation_step < 5) return;
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => {
      triggerAppLock();
    }, 60000); // 60 seconds
  };

  ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'].forEach(evt => {
    document.addEventListener(evt, resetTimer, true);
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      // Backgrounded
      setTimeout(() => {
        if (document.hidden) triggerAppLock();
      }, 60000);
    }
  });
  resetTimer();
}

function triggerAppLock() {
  if (!APP_STATE.token || !APP_STATE.user) return;
  APP_STATE.isLocked = true;
  document.getElementById('modal-app-lock').classList.add('active');
}

function unlockAppWithPin(pin) {
  apiPost('/api/auth/pin/verify', { pin }).then(res => {
    APP_STATE.isLocked = false;
    document.getElementById('modal-app-lock').classList.remove('active');
    showToast("App unlocked");
  }).catch(err => {
    showToast(err.message || "Incorrect PIN");
  });
}

// --- API HELPER ---
async function apiCall(endpoint, options = {}) {
  const headers = options.headers || {};
  if (APP_STATE.token) {
    headers['Authorization'] = `Bearer ${APP_STATE.token}`;
  }
  headers['X-Device-Id'] = APP_STATE.deviceFingerprint;
  if (!options.isFormData && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(endpoint, {
    ...options,
    headers
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.message || `Request failed with status ${res.status}`);
  }
  return data;
}

const apiGet = (url) => apiCall(url, { method: 'GET' });
const apiPost = (url, body) => apiCall(url, { method: 'POST', body: JSON.stringify(body) });
const apiDelete = (url) => apiCall(url, { method: 'DELETE' });

// --- VIEW NAVIGATION ---
function showView(viewId) {
  document.querySelectorAll('.view-container').forEach(el => el.classList.remove('active'));
  const target = document.getElementById(viewId);
  if (target) {
    target.classList.add('active');
    window.scrollTo(0, 0);
  }

  // Hide bottom nav during onboarding screens
  const isMainTab = ['view-home', 'view-wallet', 'view-history', 'view-profile', 'view-converter'].includes(viewId);
  const bottomNav = document.getElementById('bottom-nav');
  if (bottomNav) {
    bottomNav.style.display = (isMainTab && APP_STATE.user && APP_STATE.user.account_status === 'ACTIVE') ? 'flex' : 'none';
  }
}

function switchNavTab(tabName) {
  APP_STATE.activeTab = tabName;
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const btn = document.getElementById(`nav-btn-${tabName}`);
  if (btn) btn.classList.add('active');

  if (tabName === 'home') showView('view-home');
  else if (tabName === 'wallet') { loadWalletView(); showView('view-wallet'); }
  else if (tabName === 'history') { loadHistoryView(); showView('view-history'); }
  else if (tabName === 'profile') { loadProfileView(); showView('view-profile'); }
}

// --- USER PROFILE & ACTIVATION CHECK ---
async function fetchUserProfile() {
  try {
    const user = await apiGet('/api/auth/me');
    APP_STATE.user = user;
    updateUIForUser(user);

    // Route to appropriate step if not ACTIVE
    if (user.account_status !== 'ACTIVE') {
      routeIncompleteStep(user);
    } else {
      showView('view-home');
      loadHomeData();
    }
  } catch (err) {
    console.error("Auth me error:", err);
    localStorage.removeItem('tp_token');
    APP_STATE.token = null;
    showView('view-welcome');
  }
}

function routeIncompleteStep(user) {
  const step = user.activation_step;
  if (!user.full_name) {
    showView('view-onboarding-profile');
  } else if (!user.pin_hash && step <= 5) {
    showView('view-onboarding-pin');
  } else if (user.kyc_status !== 'VERIFIED') {
    showView('view-onboarding-kyc');
    loadKycOnboardingView();
  } else if (parseFloat(user.wallet_balance_inr) <= 0 && step <= 7) {
    showView('view-onboarding-funding');
  } else {
    showView('view-onboarding-activate');
    loadCurrenciesForActivation();
  }
}

function updateUIForUser(user) {
  document.querySelectorAll('.user-balance-val').forEach(el => {
    el.innerText = `₹${parseFloat(user.wallet_balance_inr).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  });
  const nameEl = document.getElementById('user-display-name');
  if (nameEl) nameEl.innerText = user.full_name || user.mobile || "Traveller";

  const avatar = document.getElementById('user-avatar');
  if (avatar) avatar.innerText = (user.full_name ? user.full_name[0] : (user.mobile ? user.mobile.slice(-2) : 'T')).toUpperCase();

  // Render checklist progress on home
  apiGet('/api/onboarding/status').then(status => {
    const banner = document.getElementById('activation-progress-card');
    if (status.is_active) {
      if (banner) banner.style.display = 'none';
      const scanCard = document.getElementById('home-scan-card');
      if (scanCard) scanCard.classList.remove('disabled');
    } else {
      if (banner) {
        banner.style.display = 'block';
        const completed = status.checklist.filter(s => s.completed).length;
        document.getElementById('checklist-steps-count').innerText = `${completed} of ${status.total_steps} steps completed`;
        document.getElementById('checklist-progress-bar').style.width = `${(completed / status.total_steps) * 100}%`;
        const next = status.checklist.find(s => !s.completed);
        document.getElementById('checklist-next-step').innerText = next ? `Next: ${next.title}` : "Complete activation to pay";
      }
    }
  }).catch(() => {});
}

// --- ONBOARDING FLOW STEPS ---

// Step 2: Request Phone OTP
async function handleSendOtp() {
  const phone = document.getElementById('login-phone').value.trim();
  if (!phone) {
    showToast("Please enter a valid mobile number");
    return;
  }
  try {
    const res = await apiPost('/api/auth/phone/otp', { mobile: phone });
    showToast(res.message);
    document.getElementById('otp-target-display').innerText = phone;
    if (res.dev_otp) {
      const devBox = document.getElementById('dev-otp-helper');
      devBox.style.display = 'block';
      document.getElementById('dev-otp-val').innerText = res.dev_otp;
    }
    showView('view-otp-verify');
    startOtpCooldownTimer();
  } catch (err) {
    showToast(err.message);
  }
}

// Step 2: Verify Phone OTP
async function handleVerifyOtp() {
  const digits = Array.from(document.querySelectorAll('.otp-box')).map(i => i.value).join('');
  const identifier = document.getElementById('login-phone').value.trim();
  if (digits.length !== 6) {
    showToast("Please enter 6-digit OTP");
    return;
  }
  try {
    const res = await apiPost('/api/auth/phone/verify', {
      identifier: identifier,
      otp: digits,
      device_id: APP_STATE.deviceFingerprint,
      device_name: navigator.userAgent.includes('Mobile') ? 'Mobile Device' : 'Desktop Browser'
    });
    APP_STATE.token = res.access_token;
    localStorage.setItem('tp_token', res.access_token);
    APP_STATE.user = res.user;
    showToast("Phone verified successfully!");
    routeIncompleteStep(res.user);
  } catch (err) {
    showToast(err.message);
  }
}

function startOtpCooldownTimer() {
  let sec = 30;
  const resendBtn = document.getElementById('btn-resend-otp');
  resendBtn.disabled = true;
  const interval = setInterval(() => {
    sec--;
    resendBtn.innerText = `Resend in ${sec}s`;
    if (sec <= 0) {
      clearInterval(interval);
      resendBtn.disabled = false;
      resendBtn.innerText = "Resend OTP";
    }
  }, 1000);
}

// Step 3: Profile Setup
async function handleProfileSubmit(e) {
  e.preventDefault();
  const full_name = document.getElementById('profile-name').value.trim();
  const email = document.getElementById('profile-email').value.trim();
  const dob = document.getElementById('profile-dob').value;

  try {
    const user = await apiPost('/api/onboarding/profile', { full_name, email, dob });
    APP_STATE.user = user;
    showToast("Profile updated!");
    showView('view-onboarding-device');
    document.getElementById('device-fp-text').innerText = APP_STATE.deviceFingerprint;
  } catch (err) {
    showToast(err.message);
  }
}

// Step 5: Set 6-Digit App PIN
let enteredPin = "";
let isConfirmingPin = false;
let firstPin = "";

function handlePinPadInput(digit) {
  if (digit === 'DEL') {
    enteredPin = enteredPin.slice(0, -1);
  } else if (enteredPin.length < 6) {
    enteredPin += digit;
  }
  updatePinDots();

  if (enteredPin.length === 6) {
    setTimeout(() => {
      if (!isConfirmingPin) {
        firstPin = enteredPin;
        enteredPin = "";
        isConfirmingPin = true;
        document.getElementById('pin-setup-title').innerText = "Confirm your 6-digit PIN";
        document.getElementById('pin-setup-desc').innerText = "Re-enter the same 6-digit PIN to confirm.";
        updatePinDots();
      } else {
        if (enteredPin !== firstPin) {
          showToast("PINs do not match. Please try again.");
          enteredPin = "";
          firstPin = "";
          isConfirmingPin = false;
          document.getElementById('pin-setup-title').innerText = "Create 6-digit App PIN";
          updatePinDots();
        } else {
          // Submit PIN
          apiPost('/api/auth/pin/set', { pin: enteredPin }).then(() => {
            showToast("PIN created successfully!");
            showView('view-onboarding-kyc');
            loadKycOnboardingView();
          }).catch(err => showToast(err.message));
        }
      }
    }, 200);
  }
}

function updatePinDots() {
  for (let i = 1; i <= 6; i++) {
    const dot = document.getElementById(`pin-dot-${i}`);
    if (dot) {
      if (i <= enteredPin.length) dot.classList.add('filled');
      else dot.classList.remove('filled');
    }
  }
}

// Step 6: KYC Verification
async function loadKycOnboardingView() {
  try {
    const kyc = await apiGet('/api/kyc/status');
    if (kyc && kyc.status === 'VERIFIED') {
      showToast("KYC already verified!");
      showView('view-onboarding-funding');
    }
  } catch (e) {}
}

async function handleKycSubmit(e) {
  e.preventDefault();
  const pan = document.getElementById('kyc-pan').value.trim().toUpperCase();
  const name = document.getElementById('kyc-name').value.trim();
  const address = document.getElementById('kyc-address').value.trim();
  const passport = document.getElementById('kyc-passport').value.trim() || null;

  try {
    const res = await apiPost('/api/kyc/submit?auto_approve=true', {
      pan_number: pan,
      full_name_on_pan: name,
      address: address,
      passport_number: passport
    });
    if (res.status === 'VERIFIED') {
      showToast("KYC Verified Instantly (Sandbox Mode)! 🎉");
      showView('view-onboarding-funding');
    } else {
      showToast("KYC Submitted for review.");
      showView('view-onboarding-funding');
    }
  } catch (err) {
    showToast(err.message);
  }
}

async function triggerSandboxKycApprove() {
  try {
    const res = await apiPost('/api/kyc/sandbox-auto-approve', {});
    showToast("KYC Approved via Sandbox Provider!");
    showView('view-onboarding-funding');
  } catch (err) {
    showToast(err.message);
  }
}

// Step 7: Funding Setup
async function handleWalletTopup(amount) {
  try {
    const order = await apiPost('/api/wallet/topup/order', { amount_inr: amount });
    // In test mode, simulate instant verified payment
    const simulatedSig = "sig_test_" + Math.random().toString(36).substring(2, 10);
    const verifyRes = await apiPost('/api/wallet/topup/verify', {
      razorpay_order_id: order.order_id,
      razorpay_payment_id: "pay_test_" + Math.random().toString(36).substring(2, 10),
      razorpay_signature: simulatedSig,
      amount_inr: amount
    });
    showToast(verifyRes.message);
    await fetchUserProfile();
    showView('view-onboarding-activate');
    loadCurrenciesForActivation();
  } catch (err) {
    showToast(err.message);
  }
}

// Step 8: Activate International Payments
let selectedCurrencies = ['TH', 'ID', 'SG'];

async function loadCurrenciesForActivation() {
  try {
    const list = await apiGet('/api/rates/currencies');
    const container = document.getElementById('activation-countries-chips');
    container.innerHTML = '';
    list.slice(0, 15).forEach(c => {
      const chip = document.createElement('div');
      chip.className = `badge badge-info ${selectedCurrencies.includes(c.country_code) ? 'selected-chip' : ''}`;
      chip.style.cursor = 'pointer';
      chip.style.padding = '8px 12px';
      chip.style.margin = '4px';
      chip.innerText = `${c.flag} ${c.code} (${c.name})`;
      chip.onclick = () => {
        if (selectedCurrencies.includes(c.country_code)) {
          selectedCurrencies = selectedCurrencies.filter(x => x !== c.country_code);
          chip.style.background = '#E8F0FE';
          chip.style.color = '#1A73E8';
        } else {
          selectedCurrencies.push(c.country_code);
          chip.style.background = '#1A73E8';
          chip.style.color = '#FFFFFF';
        }
      };
      if (selectedCurrencies.includes(c.country_code)) {
        chip.style.background = '#1A73E8';
        chip.style.color = '#FFFFFF';
      }
      container.appendChild(chip);
    });
  } catch (e) {}
}

async function handleActivateInternational() {
  const dailyLimit = document.getElementById('activate-daily-limit').value || 50000;
  const txnLimit = document.getElementById('activate-txn-limit').value || 25000;
  const femaChecked = document.getElementById('activate-fema-check').checked;
  const termsChecked = document.getElementById('activate-terms-check').checked;

  if (!femaChecked || !termsChecked) {
    showToast("Please accept FEMA declaration and terms to activate.");
    return;
  }

  try {
    const user = await apiPost('/api/onboarding/activate-international', {
      countries: selectedCurrencies.length ? selectedCurrencies : ['TH', 'SG', 'ID'],
      travel_purpose: 'TOURISM',
      custom_daily_limit_inr: parseFloat(dailyLimit),
      custom_txn_limit_inr: parseFloat(txnLimit),
      terms_accepted: true,
      fema_declaration_accepted: true
    });
    APP_STATE.user = user;
    showToast("International Payments Activated! 🌏");
    showView('view-home');
    loadHomeData();
  } catch (err) {
    showToast(err.message);
  }
}

// --- SCANNER & EMVCo QR ---
async function startScanner() {
  if (APP_STATE.user && APP_STATE.user.account_status !== 'ACTIVE') {
    showToast("Please activate your account before scanning foreign QRs.");
    routeIncompleteStep(APP_STATE.user);
    return;
  }
  showView('view-scan');

  const qrReader = document.getElementById('qr-reader');
  if (!qrReader) return;

  if (window.Html5Qrcode) {
    try {
      if (APP_STATE.qrScanner) {
        await APP_STATE.qrScanner.stop().catch(() => {});
      }
      APP_STATE.qrScanner = new Html5Qrcode("qr-reader");
      await APP_STATE.qrScanner.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        (decodedText) => {
          stopScanner();
          handleScannedData(decodedText);
        },
        () => {}
      );
    } catch (e) {
      console.warn("Camera failed to start, use paste fallback:", e);
      document.getElementById('camera-fallback-msg').style.display = 'block';
    }
  }
}

function stopScanner() {
  if (APP_STATE.qrScanner) {
    APP_STATE.qrScanner.stop().catch(() => {});
    APP_STATE.qrScanner = null;
  }
}

async function handleScannedData(rawQr) {
  try {
    const parsed = await apiPost('/api/qr/parse', { qr_data: rawQr });
    if (!parsed.amount) {
      // Ask user for amount if dynamic/static without amount
      const amountStr = prompt(`Enter amount in ${parsed.currency} for ${parsed.merchant_name}:`, "100.00");
      if (!amountStr || isNaN(parseFloat(amountStr))) {
        showToast("Amount required to proceed.");
        return;
      }
      parsed.amount = parseFloat(amountStr);
    }
    requestPaymentQuote(parsed);
  } catch (err) {
    showToast(err.message || "Failed to parse QR code");
  }
}

// --- PAYMENT QUOTE & 120S LOCK ---
async function requestPaymentQuote(parsedQR) {
  try {
    const quote = await apiPost('/api/payments/quote', {
      merchant_name: parsedQR.merchant_name,
      merchant_city: parsedQR.merchant_city,
      merchant_country: parsedQR.merchant_country,
      currency: parsedQR.currency,
      amount: parsedQR.amount
    });
    APP_STATE.activeQuote = quote;
    renderQuoteSheet(quote);
  } catch (err) {
    showToast(err.message || "Could not generate quote");
  }
}

function renderQuoteSheet(quote) {
  document.getElementById('quote-merchant-name').innerText = quote.merchant_name;
  document.getElementById('quote-location').innerText = `${quote.merchant_city || 'Overseas'}, ${quote.merchant_country || 'Global'}`;
  document.getElementById('quote-foreign-amount').innerText = `${quote.foreign_currency} ${parseFloat(quote.foreign_amount).toLocaleString()}`;
  document.getElementById('quote-fx-rate').innerText = `1 INR = ${parseFloat(quote.exchange_rate).toFixed(4)} ${quote.foreign_currency}`;
  document.getElementById('quote-base-inr').innerText = `₹${parseFloat(quote.inr_base_amount).toFixed(2)}`;
  document.getElementById('quote-fee-inr').innerText = `₹${parseFloat(quote.markup_inr).toFixed(2)} (${quote.markup_percent}%)`;
  document.getElementById('quote-gst-inr').innerText = `₹${parseFloat(quote.gst_inr).toFixed(2)} (${quote.gst_percent}%)`;
  document.getElementById('quote-total-inr').innerText = `₹${parseFloat(quote.total_inr).toFixed(2)}`;

  // Start 120s timer
  APP_STATE.quoteSecondsLeft = quote.remaining_seconds || 120;
  clearInterval(APP_STATE.quoteTimerInterval);
  updateQuoteTimerUI();
  APP_STATE.quoteTimerInterval = setInterval(() => {
    APP_STATE.quoteSecondsLeft--;
    updateQuoteTimerUI();
    if (APP_STATE.quoteSecondsLeft <= 0) {
      clearInterval(APP_STATE.quoteTimerInterval);
      document.getElementById('modal-quote-sheet').classList.remove('active');
      showToast("Quote expired! Scan again for a live rate.");
    }
  }, 1000);

  document.getElementById('modal-quote-sheet').classList.add('active');
}

function updateQuoteTimerUI() {
  const el = document.getElementById('quote-timer-text');
  const bar = document.getElementById('quote-timer-bar');
  if (el) el.innerText = `${APP_STATE.quoteSecondsLeft}s left`;
  if (bar) bar.style.width = `${(APP_STATE.quoteSecondsLeft / 120) * 100}%`;
}

// Prompt PIN for Payment
let paymentPin = "";
function openPaymentPinModal() {
  paymentPin = "";
  updatePayPinDots();
  document.getElementById('modal-pay-pin').classList.add('active');
}

function handlePayPinInput(digit) {
  if (digit === 'DEL') {
    paymentPin = paymentPin.slice(0, -1);
  } else if (paymentPin.length < 6) {
    paymentPin += digit;
  }
  updatePayPinDots();

  if (paymentPin.length === 6) {
    setTimeout(() => {
      confirmQuotePayment(paymentPin);
    }, 150);
  }
}

function updatePayPinDots() {
  for (let i = 1; i <= 6; i++) {
    const dot = document.getElementById(`pay-pin-dot-${i}`);
    if (dot) {
      if (i <= paymentPin.length) dot.classList.add('filled');
      else dot.classList.remove('filled');
    }
  }
}

async function confirmQuotePayment(pin, useBiometric = false) {
  if (!APP_STATE.activeQuote) return;
  try {
    const idempotencyKey = `IDEM-${APP_STATE.activeQuote.quote_id}-${Date.now()}`;
    const txn = await apiPost('/api/payments/confirm', {
      quote_id: APP_STATE.activeQuote.quote_id,
      pin: pin,
      use_biometric: useBiometric,
      idempotency_key: idempotencyKey
    });

    // Close modals
    clearInterval(APP_STATE.quoteTimerInterval);
    document.getElementById('modal-pay-pin').classList.remove('active');
    document.getElementById('modal-quote-sheet').classList.remove('active');

    // Show Success Screen
    renderSuccessScreen(txn);
    await fetchUserProfile();
  } catch (err) {
    showToast(err.message || "Payment failed");
    paymentPin = "";
    updatePayPinDots();
  }
}

function renderSuccessScreen(txn) {
  document.getElementById('success-amount').innerText = `₹${parseFloat(txn.inr_amount).toFixed(2)}`;
  document.getElementById('success-merchant').innerText = txn.merchant_name;
  document.getElementById('success-foreign').innerText = `${txn.foreign_currency} ${parseFloat(txn.foreign_amount).toFixed(2)}`;
  document.getElementById('success-ref').innerText = txn.settlement_id || txn.id;
  document.getElementById('btn-download-pdf-receipt').onclick = () => {
    window.open(`/api/payments/${txn.id}/receipt?token=${APP_STATE.token}`, '_blank');
  };
  showView('view-success');
}

// --- HOME & VIEWS DATA ---
async function loadHomeData() {
  try {
    const txns = await apiGet('/api/wallet/transactions');
    const container = document.getElementById('recent-txns-list');
    container.innerHTML = '';
    if (txns.length === 0) {
      container.innerHTML = '<p style="color:var(--text-secondary);font-size:13px;text-align:center;padding:12px;">No transactions yet. Scan a QR to pay.</p>';
    } else {
      txns.slice(0, 5).forEach(t => {
        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.justifyContent = 'space-between';
        item.style.alignItems = 'center';
        item.style.padding = '10px 0';
        item.style.borderBottom = '1px solid var(--border-light)';
        item.innerHTML = `
          <div>
            <div style="font-weight:600;font-size:14px;">${t.merchant_name || t.txn_type}</div>
            <div style="font-size:11px;color:var(--text-secondary);">${new Date(t.created_at).toLocaleDateString()} • <span class="badge ${t.status === 'SETTLED' ? 'badge-success' : 'badge-warning'}">${t.status}</span></div>
          </div>
          <div style="text-align:right;">
            <div style="font-weight:700;font-size:14px;color:${t.txn_type === 'WALLET_TOPUP' ? 'var(--success)' : 'var(--text-primary)'};">
              ${t.txn_type === 'WALLET_TOPUP' ? '+' : '-'}₹${parseFloat(t.inr_amount).toFixed(2)}
            </div>
            ${t.foreign_currency ? `<div style="font-size:11px;color:var(--text-secondary);">${t.foreign_currency} ${parseFloat(t.foreign_amount).toFixed(2)}</div>` : ''}
          </div>
        `;
        container.appendChild(item);
      });
    }
  } catch (e) {}
}

async function loadHistoryView() {
  try {
    const txns = await apiGet('/api/wallet/transactions');
    const container = document.getElementById('full-history-list');
    container.innerHTML = '';
    txns.forEach(t => {
      const card = document.createElement('div');
      card.className = 'card';
      card.style.marginBottom = '10px';
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
          <span style="font-weight:700;font-size:15px;">${t.merchant_name || t.txn_type}</span>
          <span style="font-weight:700;color:${t.status === 'SETTLED' ? 'var(--success)' : 'var(--danger)'};">₹${parseFloat(t.inr_amount).toFixed(2)}</span>
        </div>
        <div style="font-size:12px;color:var(--text-secondary);margin-bottom:8px;">
          ${new Date(t.created_at).toLocaleString()} • Status: <span class="badge ${t.status === 'SETTLED' ? 'badge-success' : 'badge-warning'}">${t.status}</span>
        </div>
        ${t.foreign_amount ? `<div style="font-size:12px;margin-bottom:8px;">Local Currency: <b>${t.foreign_currency} ${parseFloat(t.foreign_amount).toFixed(2)}</b></div>` : ''}
        ${t.settlement_id ? `<div style="font-size:11px;color:var(--text-secondary);margin-bottom:8px;">Rail Ref: ${t.settlement_id}</div>` : ''}
        <button class="btn btn-secondary" style="padding:6px 12px;font-size:12px;" onclick="window.open('/api/payments/${t.id}/receipt?token=${APP_STATE.token}', '_blank')">Download PDF Receipt</button>
      `;
      container.appendChild(card);
    });
  } catch (e) {}
}

async function loadProfileView() {
  if (!APP_STATE.user) return;
  document.getElementById('prof-name').innerText = APP_STATE.user.full_name || 'Traveller';
  document.getElementById('prof-mobile').innerText = APP_STATE.user.mobile || '';
  document.getElementById('prof-email').innerText = APP_STATE.user.email || '';
  document.getElementById('prof-kyc-badge').innerText = APP_STATE.user.kyc_status;
  document.getElementById('prof-account-status').innerText = APP_STATE.user.account_status;

  // Load devices
  apiGet('/api/onboarding/devices').then(devs => {
    const list = document.getElementById('prof-device-list');
    list.innerHTML = '';
    devs.forEach(d => {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.justifyContent = 'space-between';
      row.style.alignItems = 'center';
      row.style.padding = '8px 0';
      row.innerHTML = `
        <div>
          <div style="font-size:13px;font-weight:600;">${d.device_name} ${d.is_current ? '(This device)' : ''}</div>
          <div style="font-size:11px;color:var(--text-secondary);">ID: ${d.device_id.substring(0, 10)}...</div>
        </div>
        ${!d.is_current ? `<button class="btn btn-outline-danger" style="width:auto;padding:4px 8px;font-size:11px;" onclick="revokeDevice('${d.device_id}')">Revoke</button>` : ''}
      `;
      list.appendChild(row);
    });
  }).catch(() => {});
}

async function revokeDevice(deviceId) {
  try {
    await apiDelete(`/api/onboarding/devices/${deviceId}`);
    showToast("Device revoked");
    loadProfileView();
  } catch (e) {
    showToast(e.message);
  }
}

// --- LANGUAGE SWITCHER ---
function applyLanguage(lang) {
  APP_STATE.language = lang;
  localStorage.setItem('tp_lang', lang);
  const dict = I18N[lang] || I18N.en;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) el.innerText = dict[key];
  });
}

// --- TOAST HELPER ---
function showToast(msg) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.innerText = msg;
  toast.style.display = 'block';
  setTimeout(() => {
    toast.style.display = 'none';
  }, 3500);
}

// --- EVENT LISTENERS REGISTRATION ---
function setupEventListeners() {
  // Navigation tabs
  document.querySelectorAll('[data-nav]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      switchNavTab(el.getAttribute('data-nav'));
    });
  });

  // OTP inputs auto-advance
  const otpInputs = document.querySelectorAll('.otp-box');
  otpInputs.forEach((input, idx) => {
    input.addEventListener('input', (e) => {
      if (input.value && idx < otpInputs.length - 1) {
        otpInputs[idx + 1].focus();
      }
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Backspace' && !input.value && idx > 0) {
        otpInputs[idx - 1].focus();
      }
    });
  });

  // Language buttons
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      applyLanguage(btn.getAttribute('data-lang'));
      showToast(`Language set to ${btn.innerText}`);
    });
  });
}

