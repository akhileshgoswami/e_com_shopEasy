import re
from datetime import datetime, timedelta, timezone

import pytest

from app.models import PasswordResetToken, User
from tests.conftest import login, reload

RESET_LINK = re.compile(r"https://shop\.example\.com/reset-password/([A-Za-z0-9_\-]+)")
NEW_PASSWORD = "N3wSecret!pass"


def request_reset(client, email):
    return client.post("/forgot-password", data={"email": email}, follow_redirects=True)


def token_from(message):
    match = RESET_LINK.search(message.body)
    assert match, "reset link missing from the plain-text body"
    assert match.group(0) in message.html
    return match.group(1)


def as_fresh_request(client, url):
    """The app fixture keeps one app context for the whole test, so
    Flask-Login's per-request user cache (g._login_user) would leak between
    test clients. Drop it so the session cookie alone decides."""
    from flask import g

    g.pop("_login_user", None)
    return client.get(url)


def submit_new_password(client, token, password=NEW_PASSWORD, confirm=None):
    return client.post(
        f"/reset-password/{token}",
        data={"password": password, "confirm_password": confirm if confirm is not None else password},
        follow_redirects=True,
    )


def test_login_page_links_to_forgot_password(client):
    html = client.get("/login").get_data(as_text=True)
    assert 'href="/forgot-password"' in html


def test_registered_email_gets_single_use_hashed_token(client, customer, mail_outbox):
    resp = request_reset(client, customer.email)
    assert resp.status_code == 200
    assert b"If an account exists for that email" in resp.data

    assert len(mail_outbox) == 1
    message = mail_outbox[0]
    assert message.recipients == [customer.email]
    assert message.subject == "Reset Your Password | ShopEasy"
    assert "Reset Password" in message.html
    assert "30 minutes" in message.html and "30 minutes" in message.body
    assert "ignore this email" in message.body

    token = token_from(message)
    records = PasswordResetToken.for_user(customer.id)
    assert len(records) == 1
    # Only the SHA-256 of the token is stored.
    assert records[0].key.id() == PasswordResetToken.hash_token(token)
    assert token not in records[0].key.id()
    expires_in = records[0].expires_at - datetime.now(timezone.utc)
    assert timedelta(minutes=29) < expires_in <= timedelta(minutes=30)


def test_unregistered_email_gets_same_response_and_no_email(client, customer, mail_outbox):
    known = request_reset(client, customer.email)
    mail_outbox.clear()
    unknown = request_reset(client, "nobody@example.com")

    assert unknown.status_code == known.status_code == 200
    assert b"If an account exists for that email" in unknown.data
    assert mail_outbox == []


def test_inactive_account_gets_no_email(client, customer, mail_outbox):
    customer.is_active = False
    customer.put()
    request_reset(client, customer.email)
    assert mail_outbox == []
    assert PasswordResetToken.for_user(customer.id) == []


def test_invalid_email_format_is_rejected(client, mail_outbox):
    resp = client.post("/forgot-password", data={"email": "not-an-email"})
    assert resp.status_code == 200
    assert b"Enter a valid email address" in resp.data
    assert mail_outbox == []


def test_reset_url_uses_base_url_not_request_host(client, customer, mail_outbox):
    client.post("/forgot-password", data={"email": customer.email}, headers={"Host": "evil.example"})
    message = mail_outbox[0]
    assert "evil.example" not in message.html
    assert RESET_LINK.search(message.body)


def test_successful_reset_changes_password_and_sends_confirmation(client, customer, mail_outbox):
    request_reset(client, customer.email)
    token = token_from(mail_outbox[0])
    mail_outbox.clear()

    form_page = client.get(f"/reset-password/{token}")
    assert form_page.status_code == 200
    assert form_page.headers["Cache-Control"] == "no-store"
    assert form_page.headers["Referrer-Policy"] == "same-origin"

    resp = submit_new_password(client, token)
    assert b"Your password has been reset" in resp.data

    user = reload(customer)
    assert user.check_password(NEW_PASSWORD)
    assert not user.check_password("Passw0rd!")
    assert user.session_version == 1

    assert len(mail_outbox) == 1
    assert mail_outbox[0].subject == "Your password was changed | ShopEasy"
    assert mail_outbox[0].recipients == [customer.email]
    # Never email the password itself.
    assert NEW_PASSWORD not in mail_outbox[0].html + mail_outbox[0].body

    assert b"Welcome back" in login(client, customer.email, NEW_PASSWORD).data


def test_token_cannot_be_reused(client, customer, mail_outbox):
    request_reset(client, customer.email)
    token = token_from(mail_outbox[0])
    submit_new_password(client, token)

    resp = submit_new_password(client, token, password="An0ther!pass")
    assert resp.status_code == 400
    assert b"already been used" in resp.data
    assert reload(customer).check_password(NEW_PASSWORD)


def test_expired_token_is_rejected(client, customer, mail_outbox):
    request_reset(client, customer.email)
    token = token_from(mail_outbox[0])
    record = PasswordResetToken.key_for(token).get()
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    record.put()

    page = client.get(f"/reset-password/{token}")
    assert page.status_code == 400
    assert b"Link expired" in page.data

    submit_new_password(client, token)
    assert reload(customer).check_password("Passw0rd!")


@pytest.mark.parametrize("token", ["not-a-real-token", "x" * 500])
def test_invalid_token_is_rejected(client, customer, token):
    page = client.get(f"/reset-password/{token}")
    assert page.status_code == 400
    assert b"Invalid link" in page.data
    assert submit_new_password(client, token).status_code == 400
    assert reload(customer).check_password("Passw0rd!")


def test_new_request_supersedes_older_link(client, customer, mail_outbox):
    request_reset(client, customer.email)
    request_reset(client, customer.email)
    first, second = token_from(mail_outbox[0]), token_from(mail_outbox[1])

    assert submit_new_password(client, first).status_code == 400
    assert b"Your password has been reset" in submit_new_password(client, second).data


def test_weak_and_mismatched_passwords_are_rejected(client, customer, mail_outbox):
    request_reset(client, customer.email)
    token = token_from(mail_outbox[0])

    resp = submit_new_password(client, token, password="onlyletters")
    assert b"at least one letter and one number" in resp.data
    resp = submit_new_password(client, token, password="short1")
    assert b"at least 8 characters" in resp.data
    resp = submit_new_password(client, token, confirm="Different1!")
    assert b"Passwords must match" in resp.data
    assert reload(customer).check_password("Passw0rd!")
    # The token survives failed attempts.
    assert PasswordResetToken.key_for(token).get().used_at is None


def test_per_account_hourly_limit(client, customer, mail_outbox):
    for _ in range(5):
        resp = request_reset(client, customer.email)
        assert b"If an account exists for that email" in resp.data
    assert len(mail_outbox) == 3


def test_reset_signs_out_existing_sessions(app, customer, mail_outbox):
    victim_session = app.test_client()
    login(victim_session, customer.email)
    assert as_fresh_request(victim_session, "/orders").status_code == 200

    other = app.test_client()
    as_fresh_request(other, "/")
    request_reset(other, customer.email)
    submit_new_password(other, token_from(mail_outbox[0]))

    resp = as_fresh_request(victim_session, "/orders")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_change_password_keeps_current_session_and_signs_out_others(app, customer, mail_outbox):
    current = app.test_client()
    other = app.test_client()
    login(current, customer.email)
    login(other, customer.email)

    resp = current.post(
        "/profile/password",
        data={"current_password": "Passw0rd!", "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        follow_redirects=True,
    )
    assert b"Password changed successfully" in resp.data
    assert as_fresh_request(current, "/orders").status_code == 200
    assert as_fresh_request(other, "/orders").status_code == 302
    assert [m.subject for m in mail_outbox] == ["Your password was changed | ShopEasy"]


def test_existing_sessions_without_version_still_load(app, customer):
    """Users who never changed their password keep their plain-id session."""
    assert customer.get_id() == str(customer.id)
    assert User.from_session_id(str(customer.id)).id == customer.id
    assert User.from_session_id(f"{customer.id}:3") is None
    assert User.from_session_id("garbage:x") is None


@pytest.fixture()
def rate_limited_client(monkeypatch):
    from app.config import TestingConfig
    from tests.conftest import _reset_emulator

    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    _reset_emulator()
    from app import create_app
    from app.extensions import limiter, ndb

    application = create_app("testing")
    with application.app_context(), ndb.client.context(cache_policy=False):
        limiter.reset()
        yield application.test_client()
        limiter.reset()


def test_forgot_password_is_rate_limited_per_ip(rate_limited_client):
    statuses = [
        rate_limited_client.post("/forgot-password", data={"email": f"user{i}@example.com"}).status_code
        for i in range(6)
    ]
    assert statuses[:5] == [302] * 5
    assert statuses[5] == 429
    # Viewing the page isn't limited.
    assert rate_limited_client.get("/forgot-password").status_code == 200


def test_reset_form_submits_over_https_with_csrf(app, customer, mail_outbox):
    """Regression: over HTTPS Flask-WTF requires a same-origin Referer, so the
    reset page must not send Referrer-Policy: no-referrer."""
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()
    https = {"base_url": "https://shop.example.com"}

    page = client.get("/forgot-password", **https)
    csrf = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page.get_data(as_text=True)).group(1)
    client.post(
        "/forgot-password",
        data={"email": customer.email, "csrf_token": csrf},
        headers={"Referer": "https://shop.example.com/forgot-password"},
        **https,
    )
    token = token_from(mail_outbox[0])

    page = client.get(f"/reset-password/{token}", **https)
    # What the browser does with this policy on a same-site form POST:
    assert page.headers["Referrer-Policy"] in ("same-origin", "strict-origin-when-cross-origin")
    csrf = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page.get_data(as_text=True)).group(1)
    resp = client.post(
        f"/reset-password/{token}",
        data={"password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD, "csrf_token": csrf},
        headers={"Referer": f"https://shop.example.com/reset-password/{token}"},
        **https,
    )
    assert resp.status_code == 302, resp.get_data(as_text=True)[:300]
    assert reload(customer).check_password(NEW_PASSWORD)

    # Without a Referer (what no-referrer caused) Flask-WTF rejects it.
    missing = client.post("/forgot-password", data={"email": customer.email, "csrf_token": csrf}, **https)
    assert missing.status_code == 400
