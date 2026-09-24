from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from tests.conftest import admin_login, login

COOKIE = "shopeasy_session"


def _session_expiry(resp):
    for header in resp.headers.getlist("Set-Cookie"):
        if header.startswith(COOKIE + "="):
            for part in header.split(";"):
                if part.strip().lower().startswith("expires="):
                    return parsedate_to_datetime(part.split("=", 1)[1])
    return None


def test_login_cookie_outlives_the_browser_for_eight_hours(client, customer):
    resp = client.post("/login", data={"email": customer.email, "password": "Passw0rd!"})
    expires = _session_expiry(resp)
    assert expires is not None, "session cookie must not be a browser-session cookie"
    remaining = expires - datetime.now(timezone.utc)
    assert timedelta(hours=7, minutes=58) < remaining <= timedelta(hours=8, minutes=1)


def test_each_visit_extends_the_session(client, customer):
    login(client, customer.email)
    resp = client.get("/orders")
    assert resp.status_code == 200
    assert _session_expiry(resp) is not None  # refreshed on every request


def test_admin_login_is_permanent_too(client, admin_user):
    resp = client.post("/admin/login", data={"email": admin_user.email, "password": "Passw0rd!"})
    assert _session_expiry(resp) is not None


def test_logout_still_ends_the_session(client, customer):
    login(client, customer.email)
    client.get("/logout")
    assert client.get("/orders").status_code == 302


def test_lifetime_is_configurable(app):
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(minutes=480)
    assert app.config["REMEMBER_COOKIE_DURATION"] == timedelta(days=14)
