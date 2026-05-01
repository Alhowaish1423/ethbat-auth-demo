import os
import io
import json
import base64
from functools import wraps

import qrcode
import pyotp
import requests
from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

# ── Ethbat backend config ─────────────────────────────────────────────────────
ETHBAT_URL = "https://ethbat-backend.onrender.com"
ETHBAT_API_KEY = "test-api-key-001"


# ── Helpers ───────────────────────────────────────────────────────────────────
def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(users: dict) -> None:
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def make_qr_b64(uri: str) -> str:
    """Any URI → base64-encoded PNG for embedding in <img src=...>."""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in_user"):
            flash("Please log in to access that page.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── Registration ──────────────────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        users = load_users()
        if username in users:
            flash("Username already taken. Please choose another.", "error")
            return render_template("register.html")

        # TOTP secret (for Google Authenticator tab)
        totp_secret = pyotp.random_base32()
        totp_uri    = pyotp.TOTP(totp_secret).provisioning_uri(
            name=username, issuer_name="Ethbat Auth Demo"
        )

        session["reg_username"] = username
        session["reg_password"] = generate_password_hash(password)
        session["reg_secret"]   = totp_secret

        # Ethbat enrollment session (for Ethbat tab) — optional, may fail if backend is down
        ethbat_qr_b64  = None
        ethbat_code    = None
        try:
            r = requests.post(
                f"{ETHBAT_URL}/integrator/enroll/start",
                headers={"x-api-key": ETHBAT_API_KEY},
                timeout=3,
            )
            d = r.json()
            if d.get("ok"):
                session["reg_ethbat_session_id"] = d["session_id"]
                ethbat_qr_b64 = make_qr_b64(d["qr_data"])
                ethbat_code   = d["code_6digit"]
        except Exception:
            pass  # Ethbat backend offline — show Google Auth tab only

        return render_template(
            "verify_register.html",
            username=username,
            totp_qr_b64=make_qr_b64(totp_uri),
            totp_secret=totp_secret,
            ethbat_qr_b64=ethbat_qr_b64,
            ethbat_code=ethbat_code,
        )

    return render_template("register.html")


@app.route("/verify-register", methods=["POST"])
def verify_register():
    """Complete registration via Google Authenticator (TOTP code submitted)."""
    username      = session.get("reg_username")
    password_hash = session.get("reg_password")
    secret        = session.get("reg_secret")

    if not username or not password_hash or not secret:
        flash("Registration session expired. Please start again.", "error")
        return redirect(url_for("register"))

    code = request.form.get("code", "").strip()
    if not pyotp.TOTP(secret).verify(code):
        totp_uri  = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="Ethbat Auth Demo")
        ethbat_qr_b64 = None
        ethbat_code   = None
        ethbat_sid    = session.get("reg_ethbat_session_id")
        if ethbat_sid:
            try:
                r = requests.get(
                    f"{ETHBAT_URL}/integrator/enroll/status",
                    params={"session_id": ethbat_sid},
                    headers={"x-api-key": ETHBAT_API_KEY},
                    timeout=3,
                )
                s = r.json().get("status")
                if s == "pending":
                    # rebuild Ethbat QR from session data (re-render page)
                    pass
            except Exception:
                pass
        flash("Invalid code. Please check your authenticator app and try again.", "error")
        return render_template(
            "verify_register.html",
            username=username,
            totp_qr_b64=make_qr_b64(totp_uri),
            totp_secret=secret,
            ethbat_qr_b64=None,  # session still active, JS continues polling
            ethbat_code=None,
        )

    # TOTP verified — save user with TOTP secret, no Ethbat
    users = load_users()
    users[username] = {"password": password_hash, "secret": secret, "ethbat_link_id": None}
    save_users(users)

    _clear_reg_session()
    flash("Registration successful! You can now log in.", "success")
    return redirect(url_for("login"))


@app.route("/api/ethbat-register-poll")
def ethbat_register_poll():
    """JS polls this during registration to detect when Ethbat app completes enrollment."""
    session_id    = session.get("reg_ethbat_session_id")
    username      = session.get("reg_username")
    password_hash = session.get("reg_password")

    if not session_id or not username:
        return jsonify({"ok": False, "error": "No registration session"})

    try:
        r = requests.get(
            f"{ETHBAT_URL}/integrator/enroll/status",
            params={"session_id": session_id},
            headers={"x-api-key": ETHBAT_API_KEY},
            timeout=5,
        )
        data = r.json()
    except Exception:
        return jsonify({"ok": False, "error": "Backend unreachable"})

    if data.get("status") == "linked":
        # Save user with Ethbat link_id, no TOTP secret
        users = load_users()
        users[username] = {
            "password": password_hash,
            "secret": None,
            "ethbat_link_id": data["link_id"],
        }
        save_users(users)
        _clear_reg_session()

    return jsonify({"ok": True, "status": data.get("status")})


def _clear_reg_session():
    for key in ("reg_username", "reg_password", "reg_secret", "reg_ethbat_session_id"):
        session.pop(key, None)


# ── Login ─────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        users = load_users()
        user  = users.get(username)

        if not user or not check_password_hash(user["password"], password):
            flash("Invalid username or password.", "error")
            return render_template("login.html")

        method = request.form.get("method", "")

        if method == "ethbat":
            if not user.get("ethbat_link_id"):
                flash("This account is not set up with Ethbat.", "error")
                return render_template("login.html")
            session["pending_2fa_user"] = username
            return redirect(url_for("login_ethbat"))

        if method == "google":
            if not user.get("secret"):
                flash("This account is not set up with Google Authenticator.", "error")
                return render_template("login.html")
            session["pending_2fa_user"] = username
            return redirect(url_for("login_verify"))

        flash("Please select an authentication method.", "error")
        return render_template("login.html")

    return render_template("login.html")


@app.route("/login-verify", methods=["GET", "POST"])
def login_verify():
    """Google Authenticator TOTP step."""
    username = session.get("pending_2fa_user")
    if not username:
        flash("Please enter your username and password first.", "error")
        return redirect(url_for("login"))

    users     = load_users()
    user_data = users.get(username, {})

    # User enrolled via Ethbat, has no TOTP secret
    if not user_data.get("secret"):
        return redirect(url_for("login_ethbat"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if pyotp.TOTP(user_data["secret"]).verify(code):
            session.pop("pending_2fa_user", None)
            session["logged_in_user"] = username
            return redirect(url_for("success"))
        flash("Invalid authenticator code. Please try again.", "error")

    return render_template("login_verify.html", username=username)


@app.route("/login-ethbat")
def login_ethbat():
    """Start an Ethbat push-notification challenge and show the waiting page."""
    username = session.get("pending_2fa_user")
    if not username:
        flash("Please enter your username and password first.", "error")
        return redirect(url_for("login"))

    users   = load_users()
    link_id = users.get(username, {}).get("ethbat_link_id")
    if not link_id:
        flash("Ethbat is not set up for this account.", "error")
        return redirect(url_for("login_verify"))

    try:
        r = requests.post(
            f"{ETHBAT_URL}/startChallenge",
            json={"link_id": link_id, "origin_country": "SA"},
            headers={"x-api-key": ETHBAT_API_KEY},
            timeout=5,
        )
        data = r.json()
    except Exception:
        flash("Could not reach Ethbat backend.", "error")
        return redirect(url_for("login"))

    if not data.get("ok"):
        flash(f"Could not start challenge: {data.get('error', 'unknown error')}", "error")
        return redirect(url_for("login"))

    session["ethbat_challenge_id"] = data["challenge_id"]
    has_totp = bool(users.get(username, {}).get("secret"))
    return render_template("ethbat_verify.html", username=username, has_totp=has_totp)


@app.route("/api/ethbat-challenge-poll")
def ethbat_challenge_poll():
    """JS polls this every 2 s waiting for the user to approve on their phone."""
    username     = session.get("pending_2fa_user")
    challenge_id = session.get("ethbat_challenge_id")

    if not challenge_id or not username:
        return jsonify({"ok": False, "error": "No active challenge"})

    try:
        r = requests.get(
            f"{ETHBAT_URL}/getChallengeStatus",
            params={"challenge_id": challenge_id},
            timeout=5,
        )
        data = r.json()
    except Exception:
        return jsonify({"ok": False, "error": "Backend unreachable"})

    status = data.get("status")

    if status == "approved":
        session.pop("pending_2fa_user", None)
        session.pop("ethbat_challenge_id", None)
        session["logged_in_user"] = username

    return jsonify({"ok": True, "status": status})


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/success")
@login_required
def success():
    username  = session["logged_in_user"]
    users     = load_users()
    auth_method = "Ethbat" if users.get(username, {}).get("ethbat_link_id") else "Google Authenticator"
    return render_template("success.html", username=username, auth_method=auth_method)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
    app.run(debug=True, port=5000)
