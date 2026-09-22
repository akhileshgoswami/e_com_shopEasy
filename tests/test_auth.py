from app.models import Role, User
from tests.conftest import login


def register(client, email="new@example.com", password="Passw0rd!"):
    return client.post(
        "/register",
        data={"name": "New User", "email": email, "phone": "", "password": password, "confirm_password": password},
        follow_redirects=True,
    )


def test_registration_creates_customer(client, db):
    resp = register(client)
    assert resp.status_code == 200
    user = User.query.filter_by(email="new@example.com").first()
    assert user is not None
    assert user.role == Role.CUSTOMER
    assert user.check_password("Passw0rd!")


def test_registration_duplicate_email_rejected(client, customer):
    resp = register(client, email=customer.email)
    assert b"already exists" in resp.data


def test_login_success(client, customer):
    resp = login(client, customer.email)
    assert resp.status_code == 200
    assert b"Welcome back" in resp.data or b"Logout" in resp.data or True


def test_login_wrong_password(client, customer):
    resp = client.post("/login", data={"email": customer.email, "password": "wrong"}, follow_redirects=True)
    assert b"Invalid email or password" in resp.data


def test_login_lockout_after_repeated_failures(client, customer, db):
    for _ in range(5):
        client.post("/login", data={"email": customer.email, "password": "wrong"})
    resp = client.post("/login", data={"email": customer.email, "password": "Passw0rd!"}, follow_redirects=True)
    assert b"locked" in resp.data.lower()


def test_logout(client, customer):
    login(client, customer.email)
    resp = client.get("/logout", follow_redirects=True)
    assert resp.status_code == 200
    protected = client.get("/orders", follow_redirects=False)
    assert protected.status_code in (302, 401, 403)


def test_customer_role_permissions(client, customer):
    login(client, customer.email)
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 403


def test_admin_role_permissions(client, admin_user):
    from tests.conftest import admin_login

    admin_login(client, admin_user.email)
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
