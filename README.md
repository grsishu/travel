# TravelPay 🌏💳
> **GPay-style Full-Stack Cross-Border QR Payment PWA for Indian Travellers abroad.**

TravelPay lets Indian travellers scan local foreign merchant QR codes (Thailand's **PromptPay**, Indonesia's **QRIS**, Singapore's **SGQR**, Vietnam's **VietQR**, and JSON merchant QRs), converts foreign currency into INR with transparent forex fees and GST, collects payments in INR via a payment gateway (Razorpay), and settles foreign merchants in their local currency via pluggable settlement rails (Wise, Airwallex, Sandbox).

---

## 🌟 Key Features

1. **GPay-Style Mobile-First PWA**:
   - Google clean design aesthetic (Google Sans/Inter typography, Google Blue `#1A73E8`, rounded cards, bottom navigation).
   - Installable PWA with offline application shell caching (`manifest.json` + `sw.js`).
   - 60-second inactivity lock with 6-digit App PIN unlock.
   - Multi-language support: English, Hindi (हिंदी), and Tamil (தமிழ்).

2. **Sequential Activation Gate (Mandatory & Strictly Backend Enforced)**:
   - **Step 1: Splash & Welcome**: Animated brand screen to "Get Started".
   - **Step 2: Mobile + OTP**: Country picker, 6-digit auto-advancing OTP, 5-min expiry, 3-attempt limit, 30s resend cooldown. Also supports Email + Password login.
   - **Step 3: Profile Setup**: Full Name, Email, Date of Birth with 18+ enforcement.
   - **Step 4: Device Binding**: Registers device ID + User Agent. "Your Devices" screen with remote logout capability.
   - **Step 5: App PIN & Biometrics**: 6-digit App PIN hashed with bcrypt. WebAuthn passkey biometric unlock. Wrong PIN 3 times triggers 30-minute lockout.
   - **Step 6: KYC (PAN Verification)**: Indian PAN validation (`[A-Z]{5}[0-9]{4}[A-Z]{1}`), Fernet AES encryption at rest, masked PAN display, selfie & document upload. Includes `SandboxKycProvider` for one-click test approvals and an Admin review queue.
   - **Step 7: Wallet Funding**: Add INR balance through Razorpay Checkout.
   - **Step 8: Activate International Payments**: Select destination countries, accept FEMA/LRS & Travel Purpose declarations, set custom daily and per-transaction limits.
   - **Step 9: Unlock**: Only accounts in `ACTIVE` state with `VERIFIED` KYC can generate quotes or scan and pay.

3. **Universal EMVCo TLV & JSON QR Parser**:
   - Parses EMVCo Merchant-Presented TLV QR codes: Tag 59 (Merchant Name), Tag 60 (City), Tag 58 (Country), Tag 53 (ISO 4217 Numeric to Alpha mapped), Tag 54 (Amount), and Tag 63 (CRC16-CCITT checksum validation).
   - Rejects corrupted or tampered QR codes.
   - Camera scanning via `html5-qrcode` (bundled offline) with paste fallback.
   - Built-in **Merchant QR Generator** test page (`/merchant-qr`).

4. **Transparent Currency & Quote Locking**:
   - Dynamic currency rates engine for ~160 currencies from `open.er-api.com` cached for 5 minutes with fallback table.
   - Exact ISO 4217 minor unit decimals handling (JPY 0 decimals, KWD 3, USD 2).
   - **Pure `Decimal` calculations** (zero float rounding drift).
   - Transparent fee breakdown: Foreign Amount &rarr; Base INR &rarr; 2% Forex Markup &rarr; 18% GST on Markup &rarr; Total INR.
   - **120-second server-side quote lock** with live circular progress timer.

5. **State Machine & Settlement Abstraction**:
   - `QUOTED` &rarr; `PAYMENT_PENDING` &rarr; `PAID` &rarr; `SETTLING` &rarr; `SETTLED`.
   - Pluggable `SettlementProvider`:
     - `SandboxSettlementProvider` (instant simulation with failure detection)
     - `WiseProvider` (TransferWise platform skeleton)
     - `AirwallexProvider` (Airwallex global payouts skeleton)
   - **Automatic Wallet Refund**: If settlement fails at the foreign merchant bank, funds are automatically refunded back to the user's INR wallet balance.

6. **Downloadable PDF Receipts**:
   - Clean, professional cross-border payment receipts generated using ReportLab, detailing foreign amount, live rate, base INR, markup, GST, total INR, and regulatory LRS notes.

7. **Admin Operations Dashboard (`/admin`)**:
   - User table with freeze/unfreeze account control.
   - KYC approval queue with Approve / Reject controls.
   - Transaction monitor with manual refund trigger.
   - Fraud review queue (velocity checks, new-device flags, amount anomalies).
   - Configurable markup fee and GST rates.

---

## 🏗️ Project Architecture

```
travel/
├── app/
│   ├── main.py                     # FastAPI entrypoint, middlewares, mounts
│   ├── config.py                   # Pydantic v2 settings, secrets, timeouts
│   ├── db.py                       # SQLAlchemy engine & session factory
│   ├── models.py                   # ORM models (User, Device, KYC, Quote, Txn, etc.)
│   ├── schemas.py                  # Pydantic validation schemas
│   ├── deps.py                     # JWT token decoding, auth dependencies
│   ├── services/
│   │   ├── otp.py                  # OtpProvider (Console, Twilio, MSG91)
│   │   ├── rates.py                # Live FX rates with 5m TTL cache & minor units
│   │   ├── emv_qr.py               # EMVCo TLV parser & CRC-16 engine
│   │   ├── quotes.py               # 120s locked quote engine
│   │   ├── payments.py             # Payment execution & wallet deduction
│   │   ├── fraud.py                # Velocity, anomaly & risk engine
│   │   ├── kyc.py                  # Fernet PAN encryption & KYC approval
│   │   ├── activation.py           # Sequential gating & LRS tracking
│   │   ├── pdf_receipt.py          # ReportLab PDF receipt generator
│   │   └── settlement/             # Settlement Rails Abstraction
│   │       ├── base.py             # SettlementProvider (ABC)
│   │       ├── sandbox.py          # SandboxSettlementProvider
│   │       ├── wise.py             # Wise platform skeleton
│   │       └── airwallex.py        # Airwallex payout skeleton
│   ├── routers/                    # Modular API endpoints
│   ├── static/                     # PWA CSS, JS, manifest, SW, vendor libs
│   └── templates/                  # index.html (PWA), admin.html, qr_generator.html
├── tests/                          # 22 automated pytest test suites
├── seed.py                         # Seeding script for demo & admin users
├── Dockerfile                      # Production Docker container
├── docker-compose.yml              # Multi-container setup (Web + PostgreSQL 16)
├── requirements.txt                # Python dependencies
├── .env.example                    # Template environment variables
└── README.md                       # Documentation
```

---

## ⚡ Quick Start (Local Development)

### 1. Prerequisites
- Python 3.10+ installed
- Git

### 2. Setup & Database Seeding
```bash
# Clone and enter directory
cd travel

# Install dependencies
pip install -r requirements.txt

# Run the database seeder (creates tables and test users)
python seed.py
```

### 3. Run the App
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser to:
- **TravelPay Mobile PWA App**: [http://localhost:8000](http://localhost:8000)
- **Admin Operations Console**: [http://localhost:8000/admin](http://localhost:8000/admin)
- **Merchant QR Generator**: [http://localhost:8000/merchant-qr](http://localhost:8000/merchant-qr)
- **Swagger Interactive API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 👥 Seeded Demo Accounts

| Role | Identifier / Email | Password / OTP | App PIN | Status & Details |
|------|-------------------|----------------|---------|------------------|
| **Administrator** | `admin@travelpay.internal` | `Admin@123` | - | Full admin privileges on `/admin` |
| **Active Demo User** | `+919876543210` / `demo@travelpay.internal` | `Demo@123` / Any OTP | `123456` | **ACTIVE**, KYC Verified, Pre-funded **₹25,000**, Visiting TH/ID/SG |
| **Inactive Test User**| `+919876543211` | Any OTP | - | **INACTIVE** (Mid-onboarding Step 3 to test activation gate) |

---

## 🧪 Running the Automated Test Suite

The test suite covers:
- OTP generation, expiry, 3-attempt limit, and 30s resend cooldown.
- The activation gate: payments and quotes rejected at every incomplete step.
- App PIN verification and 30-minute lockout on 3 wrong attempts.
- EMVCo QR TLV parsing and CRC16-CCITT checksum validation on PromptPay, QRIS, and SGQR samples.
- ISO 4217 minor unit decimals (JPY 0, KWD 3, USD 2) and Decimal precision.
- Transparent 2% fee and 18% GST calculation.
- 120-second quote validity and expiry.
- Razorpay webhook signature verification and idempotency check.
- Automatic refund upon settlement failure.
- LRS annual (USD 250,000) and daily spending limit enforcement.

```bash
python -m pytest -v
```

Output:
```
======================= 22 passed in 4.17s ========================
```

---

## 🐳 Running with Docker & Docker Compose

TravelPay includes production-ready containerization with PostgreSQL 16:

```bash
# Build and start web and database services
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f web

# Stop containers
docker-compose down
```

---

## 📱 Opening on your Phone over HTTPS using ngrok

To test the **Camera QR Scanner** and **WebAuthn Biometrics** on your physical mobile device, browsers require a secure HTTPS origin. You can expose your local server using `ngrok`:

1. **Install ngrok** (if not already installed):
   Download from [ngrok.com](https://ngrok.com) or install via package manager:
   ```bash
   # Windows (winget or choco)
   winget install ngrok
   ```

2. **Start the local server**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. **Start the ngrok HTTPS tunnel**:
   ```bash
   ngrok http 8000
   ```

4. **Open on your mobile phone**:
   - Copy the `https://xxxx-xx-xx-xx.ngrok-free.app` URL.
   - Open it in Chrome or Safari on your phone.
   - **PWA Install**: Tap "Add to Home Screen" to install it like a native GPay app!
   - **Camera Scan**: Grant camera permissions and scan any merchant QR on your laptop screen.
   - **Biometrics**: Tap "🔒 Bio" to authenticate with FaceID or TouchID.

---

## 🚀 Going Live: Regulatory & Production Requirements

Operating a cross-border consumer payment app for Indian travellers requires compliance with Indian financial regulations. The following six pillars are required to transition from sandbox to live production:

### 1. RBI Authorisation / Licensed Banking Partner
- **Option A (PA-CB Licence)**: Apply for the **Payment Aggregator Cross-Border (PA-CB)** licence from the Reserve Bank of India (RBI) under the *Circular on Regulation of Payment Aggregators – Cross Border (PA-CB)* dated October 31, 2023.
- **Option B (AD Category I / II Bank Tie-up)**: Partner with an Authorized Dealer (AD Category I or II) bank in India. The bank acts as the regulated custodian of NOSTRO/VOSTRO foreign currency accounts and handles the outward remittance under the Liberalised Remittance Scheme (LRS).

### 2. FEMA & LRS Compliance
- **LRS Limit**: The Reserve Bank of India limits resident individuals to remit up to **USD 250,000** per financial year (April 1 to March 31) for permissible current account transactions (including overseas tourism and private travel).
- **Form A2 Integration**: Every cross-border merchant transaction must generate an electronic **Form A2** declaration.
- **TCS (Tax Collected at Source)**: Under Section 206C(1G) of the Income Tax Act, TCS applies to overseas tour packages and remittances beyond ₹7,00,000 in a financial year (0% up to ₹7 lakh for education/medical, 20% beyond ₹7 lakh for general travel).

### 3. Real KYC Provider Integration
Replace `SandboxKycProvider` by configuring `KYC_PROVIDER` in `.env`:
- Integrate with **HyperVerge**, **IDfy**, or **DigiLocker**.
- Verify PAN in real time against the NSDL / Protean database.
- Perform automated face-matching (liveness detection) between the uploaded selfie and the passport / government photo ID.

### 4. Real SMS OTP Provider Integration
Replace `ConsoleOtpProvider` by configuring `OTP_PROVIDER=msg91` or `OTP_PROVIDER=twilio`:
- **MSG91 / ValueFirst (India)**: Requires DLT (Distributed Ledger Technology) registration on telecom operator portals (e.g. Jio, Airtel, Vil) with approved sender IDs and SMS template IDs.
- **Twilio**: Configure `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER`.

### 5. Settlement Partner Agreement
Replace `SandboxSettlementProvider` with a licensed international FX clearing partner:
- **Wise Platform**: Connect to Wise via `WISE_API_KEY` and `WISE_PROFILE_ID` to leverage local clearing rails in Thailand (PromptPay), Singapore (FAST), Indonesia (BI-FAST), Europe (SEPA), and the UK (Faster Payments).
- **Airwallex / Nium**: Complete enterprise merchant agreements and configure API keys in `.env` to execute automated batch or instant payouts to foreign merchant acquiring networks.

### 6. Production Payment Gateway Keys
- Swap Razorpay test keys with production API credentials:
  - `RAZORPAY_KEY_ID`: `rzp_live_...`
  - `RAZORPAY_KEY_SECRET`: Production secret
  - `RAZORPAY_WEBHOOK_SECRET`: Configured in your Razorpay Dashboard webhooks tab.
- Set `TEST_MODE=false` in `.env`.

---

## 📄 License
MIT License. Built for seamless cross-border retail payments worldwide.

