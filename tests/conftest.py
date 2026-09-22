import io

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Address, Cart, Category, Product, Role, Subcategory, User


@pytest.fixture()
def app():
    application = create_app("testing")
    ctx = application.app_context()
    ctx.push()
    _db.create_all()

    yield application

    _db.session.remove()
    _db.drop_all()
    ctx.pop()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


def _create_user(db, email, role=Role.CUSTOMER, password="Passw0rd!", name="Test User"):
    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.add(Cart(user_id=user.id))
    db.session.commit()
    return user


@pytest.fixture()
def customer(db):
    return _create_user(db, "customer@example.com")


@pytest.fixture()
def other_customer(db):
    return _create_user(db, "other@example.com", name="Other User")


@pytest.fixture()
def admin_user(db):
    return _create_user(db, "admin@example.com", role=Role.ADMIN, name="Admin User")


@pytest.fixture()
def category(db):
    cat = Category(name="Electronics", slug="electronics", is_active=True)
    db.session.add(cat)
    db.session.commit()
    return cat


@pytest.fixture()
def subcategory(db, category):
    sub = Subcategory(category_id=category.id, name="Mobiles", slug="mobiles", is_active=True)
    db.session.add(sub)
    db.session.commit()
    return sub


@pytest.fixture()
def product(db, category, subcategory):
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
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture()
def address(db, customer):
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
    db.session.add(addr)
    db.session.commit()
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
