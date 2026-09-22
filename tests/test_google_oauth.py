from unittest.mock import MagicMock, patch

from app.auth.services import AuthError, AuthenticationService
from app.models import Role, User


def test_google_login_hidden_and_blocked_when_not_configured(client):
    resp = client.get("/login")
    assert b"Continue with Google" not in resp.data

    resp = client.get("/login/google", follow_redirects=True)
    assert resp.status_code == 200
    assert b"not available" in resp.data


def test_google_button_shown_when_configured(app, client):
    app.config["GOOGLE_OAUTH_ENABLED"] = True
    resp = client.get("/login")
    assert b"Continue with Google" in resp.data


@patch("app.auth.routes.oauth")
def test_google_callback_creates_new_customer(mock_oauth, app, client, db):
    app.config["GOOGLE_OAUTH_ENABLED"] = True
    mock_oauth.google.authorize_access_token.return_value = {
        "userinfo": {"email": "googleuser@example.com", "name": "Google User", "email_verified": True}
    }

    resp = client.get("/login/google/callback", follow_redirects=True)
    assert resp.status_code == 200

    user = User.query.filter_by(email="googleuser@example.com").first()
    assert user is not None
    assert user.role == Role.CUSTOMER
    assert user.name == "Google User"


@patch("app.auth.routes.oauth")
def test_google_callback_logs_in_existing_user(mock_oauth, app, client, customer, db):
    app.config["GOOGLE_OAUTH_ENABLED"] = True
    mock_oauth.google.authorize_access_token.return_value = {
        "userinfo": {"email": customer.email, "name": customer.name, "email_verified": True}
    }

    before_count = User.query.count()
    resp = client.get("/login/google/callback", follow_redirects=True)
    assert resp.status_code == 200
    assert User.query.count() == before_count  # no duplicate account created


@patch("app.auth.routes.oauth")
def test_google_callback_rejects_unverified_email(mock_oauth, app, client, db):
    app.config["GOOGLE_OAUTH_ENABLED"] = True
    mock_oauth.google.authorize_access_token.return_value = {
        "userinfo": {"email": "unverified@example.com", "name": "Nope", "email_verified": False}
    }

    resp = client.get("/login/google/callback", follow_redirects=True)
    assert resp.status_code == 200
    assert User.query.filter_by(email="unverified@example.com").first() is None


def test_find_or_create_google_user_requires_verified_email(app, db):
    try:
        AuthenticationService.find_or_create_google_user("x@example.com", "X", email_verified=False)
        assert False, "expected AuthError"
    except AuthError as exc:
        assert "verified" in str(exc).lower()


def test_find_or_create_google_user_links_existing_account(app, customer, db):
    user = AuthenticationService.find_or_create_google_user(customer.email, customer.name, email_verified=True)
    assert user.id == customer.id
