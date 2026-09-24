import json

from app.models import Order, OrderItem, OrderStatus, PaymentMethod, Product
from app.services.home_sections_service import HomeSectionsService, order_stats
from tests.conftest import admin_login, login


def _make_product(db, category, name, sku, sale_price=None):
    p = Product(
        category_id=category.id,
        name=name,
        slug=sku.lower(),
        sku=sku,
        price=1000,
        sale_price=sale_price,
        stock_quantity=10,
        is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _order(db, user, product, quantity, status=OrderStatus.DELIVERED, number="ORD-1"):
    order = Order(
        user_id=user.id,
        order_number=number,
        payment_method=PaymentMethod.COD,
        order_status=status,
        shipping_name="A",
        shipping_phone="9999999999",
        shipping_address="Street",
        shipping_city="City",
        shipping_state="State",
        shipping_postal_code="560001",
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(
        OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            quantity=quantity,
            unit_price=product.price,
            subtotal=product.price * quantity,
        )
    )
    db.session.commit()


def test_default_homepage_sections_match_previous_behaviour(client, db, category):
    _make_product(db, category, "Plain Lamp", "LAMP-1")
    _make_product(db, category, "Discount Chair", "CHAIR-1", sale_price=500)

    resp = client.get("/")
    assert b"Featured products" in resp.data
    assert b"New arrivals" in resp.data
    assert b"On sale" in resp.data
    assert b"Trending products" not in resp.data  # no orders yet -> hidden


def test_trending_ranks_by_units_and_ignores_cancelled(client, db, category, customer):
    lamp = _make_product(db, category, "Plain Lamp", "LAMP-1")
    chair = _make_product(db, category, "Oak Chair", "CHAIR-1")
    _order(db, customer, lamp, 2, number="ORD-1")
    _order(db, customer, chair, 5, number="ORD-2")
    _order(db, customer, lamp, 50, status=OrderStatus.CANCELLED, number="ORD-3")

    trending = HomeSectionsService.auto_products("trending", 8)
    assert [p.id for p in trending] == [chair.id, lamp.id]
    assert order_stats()[lamp.id] == {"units": 2, "orders": 1}

    resp = client.get("/")
    assert b"Trending products" in resp.data


def test_admin_can_hide_reorder_and_pick_products(client, admin_user, db, category):
    lamp = _make_product(db, category, "Plain Lamp", "LAMP-1")
    chair = _make_product(db, category, "Oak Chair", "CHAIR-1")
    sofa = _make_product(db, category, "Velvet Sofa", "SOFA-1")
    admin_login(client, admin_user.email)

    resp = client.get("/admin/homepage")
    assert resp.status_code == 200
    assert b"Most ordered products" in resp.data

    layout = [
        {"key": "new_arrivals", "title": "Just landed", "enabled": True, "mode": "auto", "limit": 8},
        {"key": "featured", "title": "Editor picks", "enabled": True, "mode": "manual", "product_ids": [sofa.id, lamp.id]},
        {"key": "sale", "title": "On sale", "enabled": False, "mode": "auto", "limit": 8},
        {"key": "bogus", "title": "<script>", "enabled": True},
    ]
    resp = client.post("/admin/homepage", data={"sections_json": json.dumps(layout)}, follow_redirects=True)
    assert b"Homepage sections updated." in resp.data

    saved = HomeSectionsService.get_layout()
    assert [s["key"] for s in saved] == ["new_arrivals", "featured", "sale", "trending"]

    html = client.get("/").get_data(as_text=True)
    assert html.index("Just landed") < html.index("Editor picks")
    picks = html[html.index("Editor picks"):]
    assert picks.index("Velvet Sofa") < picks.index("Plain Lamp")
    assert "Oak Chair" not in picks.split("</section>")[0]
    assert ">On sale<" not in html and "bogus" not in html


def test_manual_sale_section_skips_products_without_discount(db, category):
    full_price = _make_product(db, category, "Plain Lamp", "LAMP-1")
    discounted = _make_product(db, category, "Oak Chair", "CHAIR-1", sale_price=400)
    products = HomeSectionsService.manual_products("sale", [full_price.id, discounted.id])
    assert products == [discounted]


def test_customer_cannot_manage_homepage(client, customer):
    login(client, customer.email)
    assert client.get("/admin/homepage").status_code == 403
