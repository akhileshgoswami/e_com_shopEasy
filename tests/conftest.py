import io
import os
import urllib.error
import urllib.request

import pytest

# Tests only ever talk to the local Datastore emulator, never a real
# project. Start it with:
#   gcloud beta emulators datastore start --no-store-on-disk --consistency=1.0
os.environ.setdefault("DATASTORE_EMULATOR_HOST", "localhost:8081")
os.environ.setdefault("DATASTORE_PROJECT_ID", "e-com-test")

from app import create_app  # noqa: E402
from app.extensions import ndb  # noqa: E402
from app.models import Address, Cart, Category, Product, Role, Subcategory, User  # noqa: E402

EMULATOR_URL = f"http://{os.environ['DATASTORE_EMULATOR_HOST']}"


def _reset_emulator():
    try:
        urllib.request.urlopen(urllib.request.Request(f"{EMULATOR_URL}/reset", method="POST"), timeout=5)
    except (urllib.error.URLError, OSError):
        pytest.exit(
            f"Datastore emulator not reachable at {EMULATOR_URL}. Start it with: "
            "gcloud beta emulators datastore start --no-store-on-disk --consistency=1.0",
            returncode=2,
        )


@pytest.fixture()
def app():
    _reset_emulator()
    application = create_app("testing")
    ctx = application.app_context()
    ctx.push()
    # One NDB context for the whole test; requests made through the test
    # client reuse it. Caching is off so every read hits the emulator, like
    # separate requests would in production.
    with ndb.client.context(cache_policy=False):
        yield application
    ctx.pop()


@pytest.fixture()
def client(app):
    return app.test_client()


def reload(entity):
    """Fresh copy from the datastore (stands in for session.refresh())."""
    return entity.key.get(use_cache=False)


def _create_user(email, role=Role.CUSTOMER, password="Passw0rd!", name="Test User"):
    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password(password)
    user.put()
    Cart(id=user.id, user_id=user.id).put()
    return user


@pytest.fixture()
def customer(app):
    return _create_user("customer@example.com")


@pytest.fixture()
def other_customer(app):
    return _create_user("other@example.com", name="Other User")


@pytest.fixture()
def admin_user(app):
    return _create_user("admin@example.com", role=Role.ADMIN, name="Admin User")


@pytest.fixture()
def category(app):
    cat = Category(name="Electronics", slug="electronics", is_active=True)
    cat.put()
    return cat


@pytest.fixture()
def subcategory(category):
    sub = Subcategory(category_id=category.id, name="Mobiles", slug="mobiles", is_active=True)
    sub.put()
    return sub


@pytest.fixture()
def product(category, subcategory):
    p = Product(
        category_id=category.id,
        subcategory_id=subcategory.id,
        name="Test Phone",
        slug="test-phone",
        sku="SKU-TEST-001",
        price=1000,
        sale_price=None,
        stock_quantity=10,
        low_stock_threshold=2,
        is_active=True,
    )
    p.put()
    return p


@pytest.fixture()
def address(customer):
    addr = Address(
        user_id=customer.id,
        full_name="Test User",
        phone="9999999999",
        address_line_1="123 Main St",
        city="Bengaluru",
        state="KA",
        postal_code="560001",
        country="India",
        is_default=True,
    )
    addr.put()
    return addr


def login(client, email, password="Passw0rd!"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


def admin_login(client, email, password="Passw0rd!"):
    return client.post("/admin/login", data={"email": email, "password": password}, follow_redirects=True)


def fake_image_bytes():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="red").save(buf, format="PNG")
    buf.seek(0)
    return buf


@pytest.fixture()
def mail_outbox(app):
    """Turn email sending on and record every message. MAIL_SUPPRESS_SEND
    (TestingConfig) guarantees no SMTP connection is ever opened."""
    from app.extensions import mail

    assert app.extensions["mail"].suppress
    app.config["MAIL_ENABLED"] = True
    with mail.record_messages() as outbox:
        yield outbox


def messages_to(outbox, address):
    return [m for m in outbox if address in m.recipients]
