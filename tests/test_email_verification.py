import re
from datetime import datetime, timedelta, timezone

import pytest
from flask import g

from app.auth.services import AuthenticationService
from app.models import EmailVerificationCode, User
from tests.conftest import login, messages_to, reload

CODE_RE = re.compile(r"Your verification code: (\d{6})")


def register(client, email="new@example.com", password="Passw0rd!", name="New User"):
    return client.post(
        "/register",
        data={"name": name, "email": email, "phone": "", "password": password, "confirm_password": password},
        follow_redirects=True,
    )


def code_from(message):
    match = CODE_RE.search(message.body)
    assert match, "code missing from the plain-text body"
    assert match.group(1) in message.html
    return match.group(1)


def verify(client, code):
    return client.post("/verify-email", data={"code": code}, follow_redirects=True)


def logged_in(client):
    g.pop("_login_user", None)
    return client.get("/orders").status_code == 200


def test_signup_sends_code_and_does_not_log_in(client, mail_outbox):
    resp = register(client)
    assert b"Verify your email" in resp.data
    assert b"new@example.com" in resp.data

    user = User.by_email("new@example.com")
    assert user.email_verified is False
    assert not logged_in(client)

    assert len(mail_outbox) == 1
    message = mail_outbox[0]
    assert message.recipients == ["new@example.com"]
    assert message.subject == "Verify your email | ShopEasy"
    code = code_from(message)
    assert "10 minutes" in message.html
    # Only a keyed hash is stored.
    record = EmailVerificationCode.key_for(user.id).get()
    assert code not in record.code_hash


def test_correct_code_verifies_logs_in_and_sends_welcome(client, mail_outbox):
    register(client)
    code = code_from(mail_outbox[0])
    mail_outbox.clear()

    resp = verify(client, code[:3] + " " + code[3:])  # spaces are fine
    assert b"Your email is verified" in resp.data
    user = reload(User.by_email("new@example.com"))
    assert user.email_verified is True and user.email_verified_at is not None
    assert logged_in(client)
    assert EmailVerificationCode.key_for(user.id).get() is None
    assert [m.subject for m in mail_outbox] == ["Welcome to ShopEasy"]


def test_wrong_code_counts_attempts_then_locks(client, mail_outbox):
    register(client)
    code = code_from(mail_outbox[0])
    wrong = "000000" if code != "000000" else "111111"

    resp = verify(client, wrong)
    assert b"4 attempts left" in resp.data
    for _ in range(3):
        verify(client, wrong)
    resp = verify(client, wrong)
    assert b"Too many incorrect attempts" in resp.data
    # Even the right code is refused now.
    resp = verify(client, code)
    assert b"Too many incorrect attempts" in resp.data
    assert User.by_email("new@example.com").email_verified is False


def test_expired_code_is_rejected(client, mail_outbox):
    register(client)
    code = code_from(mail_outbox[0])
    user = User.by_email("new@example.com")
    record = EmailVerificationCode.key_for(user.id).get()
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    record.put()

    assert b"This code has expired" in verify(client, code).data
    assert reload(user).email_verified is False


@pytest.mark.parametrize("value", ["", "12345", "abcdef", "1234567"])
def test_malformed_code_is_rejected(client, mail_outbox, value):
    register(client)
    resp = verify(client, value)
    assert b"6-digit code" in resp.data or b"The code is 6 digits" in resp.data
    assert User.by_email("new@example.com").email_verified is False


def test_resend_has_cooldown_and_replaces_code(app, client, mail_outbox):
    register(client)
    first = code_from(mail_outbox[0])

    resp = client.post("/verify-email/resend", follow_redirects=True)
    assert b"Please wait" in resp.data
    assert len(mail_outbox) == 1

    user = User.by_email("new@example.com")
    record = EmailVerificationCode.key_for(user.id).get()
    record.last_sent_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    record.put()
    resp = client.post("/verify-email/resend", follow_redirects=True)
    assert b"A new code is on its way" in resp.data
    second = code_from(mail_outbox[1])
    if first != second:
        assert b"attempts left" in verify(client, first).data
    assert b"Your email is verified" in verify(client, second).data


def test_hourly_send_cap(app, client, mail_outbox):
    register(client)
    user = User.by_email("new@example.com")
    for _ in range(10):
        record = EmailVerificationCode.key_for(user.id).get()
        record.last_sent_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        record.put()
        client.post("/verify-email/resend")
    assert len(mail_outbox) == app.config["EMAIL_OTP_MAX_PER_HOUR"]


def test_unverified_login_sends_code_instead_of_logging_in(app, client, mail_outbox):
    register(client)
    client.post("/verify-email/change")
    mail_outbox.clear()
    user = User.by_email("new@example.com")
    record = EmailVerificationCode.key_for(user.id).get()
    record.last_sent_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    record.put()

    fresh = app.test_client()
    g.pop("_login_user", None)
    resp = login(fresh, "new@example.com")
    assert b"Verify your email" in resp.data
    assert not logged_in(fresh)
    code = code_from(mail_outbox[0])
    assert b"Your email is verified" in verify(fresh, code).data
    assert logged_in(fresh)


def test_wrong_password_on_unverified_account_sends_nothing(client, mail_outbox):
    register(client)
    mail_outbox.clear()
    resp = client.post("/login", data={"email": "new@example.com", "password": "Wrong1234"}, follow_redirects=True)
    assert b"Invalid email or password" in resp.data
    assert mail_outbox == []


def test_existing_accounts_are_not_affected(client, customer):
    assert customer.email_verified is None and customer.is_email_verified
    assert b"Welcome back" in login(client, customer.email).data


def test_verify_page_needs_a_pending_signup(client):
    resp = client.get("/verify-email")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_resignup_on_unverified_email_replaces_pending_account(app, client, mail_outbox):
    register(client, password="Squatter1!")
    squatter = User.by_email("new@example.com")

    owner = app.test_client()
    g.pop("_login_user", None)
    register(owner, password="Owner1234!", name="Real Owner")
    user = reload(squatter)
    assert user.id == squatter.id and user.name == "Real Owner"
    assert user.check_password("Owner1234!") and not user.check_password("Squatter1!")
    assert b"Your email is verified" in verify(owner, code_from(mail_outbox[-1])).data


def test_signup_on_verified_email_is_rejected(client, customer, mail_outbox):
    resp = register(client, email=customer.email)
    assert b"already exists" in resp.data
    assert mail_outbox == []


def test_google_claims_pending_signup_and_wipes_squatter_password(client, mail_outbox):
    register(client, password="Squatter1!")
    user = AuthenticationService.find_or_create_google_user("new@example.com", "Owner", email_verified=True)
    user = reload(user)
    assert user.email_verified is True
    assert not user.check_password("Squatter1!")


def test_new_google_user_is_verified(app):
    user = AuthenticationService.find_or_create_google_user("g@example.com", "G", email_verified=True)
    assert reload(user).email_verified is True


def test_password_reset_verifies_email(client, mail_outbox):
    register(client)
    client.post("/verify-email/change")
    client.post("/forgot-password", data={"email": "new@example.com"})
    token = re.search(r"/reset-password/([A-Za-z0-9_\-]+)", mail_outbox[-1].body).group(1)
    client.post(f"/reset-password/{token}", data={"password": "N3wPass!word", "confirm_password": "N3wPass!word"})
    assert User.by_email("new@example.com").email_verified is True
    assert b"Welcome back" in login(client, "new@example.com", "N3wPass!word").data


def test_pending_cart_action_survives_verification(client, product, mail_outbox):
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    register(client)
    resp = verify(client, code_from(mail_outbox[0]))
    assert b"Item added to your cart" in resp.data


def test_verification_can_be_switched_off(app, client, mail_outbox):
    app.config["EMAIL_VERIFICATION_REQUIRED"] = False
    resp = register(client)
    assert b"Your account has been created" in resp.data
    assert User.by_email("new@example.com").email_verified is True
    assert logged_in(client)


def test_verify_email_template_is_editable_but_code_always_shown(client, admin_user, mail_outbox):
    from app.services.email_template_service import EmailTemplateService

    EmailTemplateService.save(
        "verify_email",
        {"subject": "Code for {store_name}", "heading": "Hi", "intro": "Short.", "button_label": "Go", "note": ""},
    )
    register(client)
    message = mail_outbox[0]
    assert message.subject == "Code for ShopEasy"
    assert CODE_RE.search(message.body)
