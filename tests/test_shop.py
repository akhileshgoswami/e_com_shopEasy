from decimal import Decimal

from app.extensions import db
from app.models import Product


def _make_product(category, subcategory, name, price, sale_price=None, stock=10, sku=None):
    p = Product(
        category_id=category.id,
        subcategory_id=subcategory.id,
        name=name,
        slug=name.lower().replace(" ", "-"),
        sku=sku or f"SKU-{name.upper().replace(' ', '')}",
        price=Decimal(str(price)),
        sale_price=Decimal(str(sale_price)) if sale_price else None,
        stock_quantity=stock,
        is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


def test_search_filters_by_keyword(client, category, subcategory, db):
    _make_product(category, subcategory, "Red Shoes", 999)
    _make_product(category, subcategory, "Blue Hat", 199)

    resp = client.get("/search?q=Shoes")
    assert b"Red Shoes" in resp.data
    assert b"Blue Hat" not in resp.data


def test_product_list_price_filter(client, category, subcategory, db):
    _make_product(category, subcategory, "Cheap Item", 50)
    _make_product(category, subcategory, "Expensive Item", 5000)

    resp = client.get("/products?min_price=1000")
    assert b"Expensive Item" in resp.data
    assert b"Cheap Item" not in resp.data


def test_product_list_on_sale_filter(client, category, subcategory, db):
    _make_product(category, subcategory, "On Sale Item", 1000, sale_price=800)
    _make_product(category, subcategory, "Regular Item", 1000)

    resp = client.get("/products?on_sale=1")
    assert b"On Sale Item" in resp.data
    assert b"Regular Item" not in resp.data


def test_out_of_stock_product_shows_badge(client, category, subcategory, db):
    _make_product(category, subcategory, "Sold Out Item", 100, stock=0)
    resp = client.get("/products")
    assert b"Sold Out Item" in resp.data
    assert b"Out of stock" in resp.data


def test_inactive_product_not_listed(client, category, subcategory, db):
    p = _make_product(category, subcategory, "Hidden Item", 100)
    p.is_active = False
    db.session.commit()

    resp = client.get("/products")
    assert b"Hidden Item" not in resp.data

    resp = client.get(f"/product/{p.slug}")
    assert resp.status_code == 404


def test_pagination_limits_products_per_page(client, category, subcategory, db):
    for i in range(15):
        _make_product(category, subcategory, f"Product {i}", 100 + i)

    resp = client.get("/products?page=1")
    assert resp.status_code == 200
    resp2 = client.get("/products?page=2")
    assert resp2.status_code == 200
