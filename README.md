# Ethbat Auth Demo

A Flask web app for testing and comparing two authentication methods side by side:
- **Ethbat Authenticator** — push notification approval on your phone
- **Google Authenticator** — standard 6-digit TOTP code

---

## Quick Start (local)

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Mac/Linux: source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the development server
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## Deploying to Render (free)

1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) → **New Web Service** → connect your repo.
3. Set **Build Command** to `pip install -r requirements.txt` and **Start Command** to `gunicorn app:app`.
4. Add an environment variable: `SECRET_KEY` = any long random string.
5. Select the **Free** plan and deploy.

> **Note:** On the free Render plan, `users.json` is stored on an ephemeral disk and will reset when the service restarts. Suitable for demo/testing use.

---

## Pages & Flow

| Page | URL | Description |
|------|-----|-------------|
| Home | `/` | Login and Register buttons |
| Register | `/register` | Enter username and password |
| Set Up Authenticator | `/register` (POST) | Scan QR code with Ethbat or Google Authenticator |
| Verify Registration | `/verify-register` | Enter 6-digit code to confirm Google Auth setup |
| Login | `/login` | Enter credentials and choose auth method |
| TOTP Verify | `/login-verify` | Enter 6-digit Google Authenticator code |
| Ethbat Verify | `/login-ethbat` | Waiting page while Ethbat push notification is approved |
| Success | `/success` | Shows username, auth method used, and login time |
| Logout | `/logout` | Clears session, returns to home |

---

## How It Works

### Registration
1. User submits a username and password via `POST /register`.
2. Server generates a random Base32 TOTP secret with `pyotp.random_base32()`.
3. If the Ethbat backend is reachable, an enrollment session is started and its QR code is shown in a tab.
4. A Google Authenticator QR code is always generated (base64-embedded PNG, no files written to disk).
5. Registration data is stored temporarily in the signed cookie session.
6. User scans the QR code and submits the 6-digit code — if valid, the account is saved to `users.json`.

### Login
1. User submits username + password, then selects an auth method.
2. **Google Authenticator:** user enters the 6-digit TOTP code; `pyotp.TOTP(secret).verify(code)` checks it (allows ±30 s clock drift).
3. **Ethbat:** server starts a challenge via the Ethbat backend; browser polls every 2 s until the user approves on their phone.
4. On success, `session["logged_in_user"]` is set and the success page shows the elapsed login time.

---

## File Structure

```
flask_totp_auth/
├── app.py                     # All routes and business logic
├── users.json                 # User storage (auto-created)
├── requirements.txt
├── Procfile                   # gunicorn start command for Render
├── README.md
├── templates/
│   ├── base.html              # Shared card layout + flash messages
│   ├── index.html             # Home page
│   ├── register.html          # Registration form
│   ├── verify_register.html   # QR code display (Ethbat + Google Auth tabs)
│   ├── login.html             # Login form with method selection
│   ├── login_verify.html      # Google Authenticator code entry
│   ├── ethbat_verify.html     # Ethbat push notification waiting page
│   └── success.html           # Post-login confirmation + timer
└── static/
    └── style.css              # Sky-to-deep-blue gradient UI
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes (production) | Flask session signing key — set to a long random string |

---

## Security Notes

| Concern | This Demo | Production Recommendation |
|---------|-----------|--------------------------|
| Secret key | Read from `SECRET_KEY` env var | 32-byte random value stored in a secrets manager |
| User storage | `users.json` flat file | Database with proper access controls |
| TOTP replay | Not prevented | Track last-used code per user in DB |
| HTTPS | Not enforced locally | Always run behind TLS in production |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| Flask | Web framework |
| pyotp | TOTP secret generation and code verification |
| qrcode | QR code image generation |
| Pillow | PNG rendering (required by qrcode) |
| requests | HTTP calls to the Ethbat backend |
| gunicorn | Production WSGI server |
