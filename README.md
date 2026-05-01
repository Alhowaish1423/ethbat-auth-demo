# FlaskTOTP — Google Authenticator Demo App

A minimal Flask web app demonstrating TOTP-based two-factor authentication,
compatible with Google Authenticator, Authy, and any RFC 6238-compliant app.

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the development server
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## Pages & Flow

| Page | URL | Description |
|------|-----|-------------|
| Home | `/` | Two buttons: Login and Register |
| Register | `/register` | Enter a username |
| Scan QR | (after register POST) | Scan QR code in Google Authenticator |
| Verify | `/verify-register` | Enter 6-digit code to confirm registration |
| Login | `/login` | Enter username + 6-digit TOTP code |
| Success | `/success` | Shown after successful login |
| Logout | `/logout` | Clears session, returns to home |

---

## How It Works

### Registration
1. User submits a username via `POST /register`.
2. Server generates a random Base32 TOTP secret with `pyotp.random_base32()`.
3. A QR code PNG is created from the provisioning URI and embedded as base64 — no files written to disk.
4. Username and secret are stored **temporarily** in the server-side session.
5. User scans the QR code in their authenticator app, then submits the 6-digit code.
6. `pyotp.TOTP(secret).verify(code)` — if valid, the user is written to `users.json`.

### Login
1. User submits username + 6-digit code via `POST /login`.
2. Server looks up the stored secret in `users.json`.
3. `totp.verify(code)` is called (allows ±30 second clock drift by default).
4. If valid, `session["logged_in_user"]` is set and the user sees the success page.

---

## File Structure

```
flask_totp_auth/
├── app.py                   # All routes and business logic
├── users.json               # User storage: { "username": "TOTP_SECRET" }
├── requirements.txt
├── README.md
├── flask_session/           # Auto-created; stores server-side session files
├── templates/
│   ├── base.html            # Shared card layout + flash messages
│   ├── index.html           # Home page
│   ├── register.html        # Username input
│   ├── verify_register.html # QR code display + code entry
│   ├── login.html           # Login form
│   └── success.html         # Post-login confirmation
└── static/
    └── style.css            # Gradient card UI, forms, buttons
```

---

## Security Notes

| Concern | This Demo | Production Recommendation |
|---------|-----------|--------------------------|
| Secret key | Hardcoded string | `os.environ["SECRET_KEY"]` with a 32-byte random value |
| User storage | `users.json` flat file | Database with proper access controls |
| TOTP replay | Not prevented | Track last-used code per user in DB |
| HTTPS | Not enforced | Always run behind TLS in production |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| Flask | Web framework |
| pyotp | TOTP secret generation and code verification |
| qrcode | QR code image generation |
| Pillow | PNG rendering (required by qrcode) |
| Flask-Session | Server-side filesystem sessions |
