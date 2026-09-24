import pytest

from app.cart.services import CartError, CartService
from app.checkout.services import CheckoutService
from app.models import CartItem, Order, OrderStatus, Product, ProductSize, ProductType
from app.services.order_service import OrderService
from tests.conftest import admin_login, login, reload


@pytest.fixture()
def clothing(app):
    t = ProductType(name="Clothing", slug="clothing", size_label="Size", sizes=["S", "M", "L"], is_active=True)
    t.put()
    return t


@pytest.fixture()
def shirt(category, clothing):
    p = Product(
        category_id=category.id,
        product_type_id=clothing.id,
        name="Test Shirt",
        slug="test-shirt",
        sku="SHIRT-001",
        price=500,
        low_stock_threshold=1,
        is_active=True,
        size_label="Size",
        sizes=[ProductSize(name="S", stock_quantity=0), ProductSize(name="M", stock_quantity=5), ProductSize(name="L", stock_quantity=2)],
    )
    p.put()
    return p


def test_total_stock_follows_sizes(shirt):
    assert reload(shirt).stock_quantity == 7
    assert shirt.stock_for("M") == 5
    assert shirt.stock_for("XL") == 0


def test_product_type_crud_parses_sizes(client, admin_user):
    admin_login(client, admin_user.email)
    resp = client.post(
        "/admin/product-types/new",
        data={"name": "Footwear", "size_label": "Shoe size", "sizes": "UK 6, UK 7\nUK 8\nuk 7", "sort_order": 0, "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    t = ProductType.first(ProductType.slug == "footwear")
    assert t.sizes == ["UK 6", "UK 7", "UK 8"]
    assert t.size_label == "Shoe size"


def test_create_common_types(client, admin_user):
    admin_login(client, admin_user.email)
    client.post("/admin/product-types/defaults", follow_redirects=True)
    names = {t.name for t in ProductType.all()}
    assert {"Clothing", "Footwear"} <= names
    # Idempotent.
    client.post("/admin/product-types/defaults", follow_redirects=True)
    assert len(ProductType.all()) == len(names)


def test_admin_creates_sized_product(client, admin_user, category, clothing):
    admin_login(client, admin_user.email)
    resp = client.post(
        "/admin/products/new",
        data={
            "category_id": category.id,
            "subcategory_id": 0,
            "product_type_id": clothing.id,
            "name": "Polo",
            "sku": "polo-1",
            "price": "799.00",
            "low_stock_threshold": 2,
            "is_active": "y",
            "size_on": ["S", "L", "XXL"],  # XXL isn't a Clothing size: ignored
            "size_stock__S": "4",
            "size_stock__M": "9",  # not ticked: ignored
            "size_stock__L": "6",
            "size_stock__XXL": "50",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    product = Product.first(Product.sku == "POLO-1")
    assert product.product_type_id == clothing.id
    assert [(s.name, s.stock_quantity) for s in product.sizes] == [("S", 4), ("L", 6)]
    assert product.stock_quantity == 10


def test_admin_sized_product_requires_a_size(client, admin_user, category, clothing):
    admin_login(client, admin_user.email)
    resp = client.post(
        "/admin/products/new",
        data={
            "category_id": category.id,
            "subcategory_id": 0,
            "product_type_id": clothing.id,
            "name": "Polo",
            "sku": "polo-2",
            "price": "799.00",
            "low_stock_threshold": 2,
            "is_active": "y",
        },
        follow_redirects=True,
    )
    assert b"Select at least one size" in resp.data
    assert Product.first(Product.sku == "POLO-2") is None


def test_unsized_product_still_uses_single_stock(client, admin_user, category):
    admin_login(client, admin_user.email)
    client.post(
        "/admin/products/new",
        data={
            "category_id": category.id,
            "subcategory_id": 0,
            "product_type_id": 0,
            "name": "Kettle",
            "sku": "kettle-1",
            "price": "999.00",
            "stock_quantity": 12,
            "low_stock_threshold": 2,
            "is_active": "y",
        },
        follow_redirects=True,
    )
    product = Product.first(Product.sku == "KETTLE-1")
    assert product.sizes == []
    assert product.stock_quantity == 12


def test_inventory_update_per_size(client, admin_user, shirt):
    admin_login(client, admin_user.email)
    client.post(
        f"/admin/inventory/{shirt.id}/update",
        data={"size_stock__S": "3", "size_stock__M": "1", "size_stock__L": "", "low_stock_threshold": 1},
        follow_redirects=True,
    )
    shirt = reload(shirt)
    assert [s.stock_quantity for s in shirt.sizes] == [3, 1, 2]
    assert shirt.stock_quantity == 6


def test_cart_requires_valid_size(app, customer, shirt):
    with pytest.raises(CartError, match="select a size"):
        CartService.add_item(customer, shirt.id, 1)
    with pytest.raises(CartError, match="out of stock"):
        CartService.add_item(customer, shirt.id, 1, size="S")
    with pytest.raises(CartError, match="Only 2"):
        CartService.add_item(customer, shirt.id, 3, size="L")


def test_same_product_two_sizes_are_two_lines(client, customer, shirt, address):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": shirt.id, "quantity": 2, "size": "M"})
    client.post("/cart/add", data={"product_id": shirt.id, "quantity": 1, "size": "L"})
    client.post("/cart/add", data={"product_id": shirt.id, "quantity": 1, "size": "M"})
    lines = sorted(CartItem.all(CartItem.cart_id == customer.id), key=lambda i: i.size)
    assert [(i.size, i.quantity) for i in lines] == [("L", 1), ("M", 3)]

    resp = client.post("/checkout/place", data={"address_id": address.id, "payment_method": "cod"}, follow_redirects=True)
    assert resp.status_code == 200
    order = Order.first(Order.user_id == customer.id)
    assert sorted((i.size, i.quantity) for i in order.items) == [("L", 1), ("M", 3)]

    shirt = reload(shirt)
    assert shirt.stock_for("M") == 2
    assert shirt.stock_for("L") == 1
    assert shirt.stock_quantity == 3

    OrderService.change_status(order, OrderStatus.CANCELLED, changed_by="test")
    shirt = reload(shirt)
    assert shirt.stock_for("M") == 5
    assert shirt.stock_for("L") == 2
    assert shirt.stock_quantity == 7


def test_buy_now_with_size(client, customer, shirt, address):
    login(client, customer.email)
    resp = client.post("/buy-now", data={"product_id": shirt.id, "quantity": 1})
    assert resp.status_code == 302
    assert "/product/" in resp.headers["Location"] or "test-shirt" in resp.headers["Location"]

    client.post("/buy-now", data={"product_id": shirt.id, "quantity": 9, "size": "L"})
    summary = CheckoutService.build_summary(customer, buy_now={"product_id": shirt.id, "quantity": 9, "size": "L"})
    assert summary["cart_items"][0].size == "L"
    assert summary["cart_items"][0].quantity == 2


def test_cart_sync_drops_removed_size(app, customer, shirt):
    CartService.add_item(customer, shirt.id, 1, size="L")
    shirt.sizes = [s for s in shirt.sizes if s.name != "L"]
    shirt.put()
    cart = CartService.get_or_create_cart(customer)
    messages = CartService.sync_cart(cart)
    assert any("no longer available" in m for m in messages)
    assert cart.items == []


def test_product_page_shows_size_picker(client, shirt):
    resp = client.get(f"/product/{shirt.slug}")
    assert resp.status_code == 200
    assert b'name="size"' in resp.data
    assert b"Select size" in resp.data


def test_sized_pages_render(client, admin_user, customer, shirt, clothing, address):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": shirt.id, "quantity": 1, "size": "M"})
    resp = client.get("/cart")
    assert b"Size: <strong>M</strong>" in resp.data
    resp = client.get("/checkout")
    assert resp.status_code == 200 and b"(Size: M)" in resp.data
    client.post("/checkout/place", data={"address_id": address.id, "payment_method": "cod"})
    order = Order.first(Order.user_id == customer.id)
    assert b"Size: <strong>M</strong>" in client.get(f"/orders/{order.id}").data
    assert b"Choose size" in client.get("/products").data
    client.get("/logout")

    admin_login(client, admin_user.email)
    for url in (
        "/admin/product-types",
        "/admin/product-types/new",
        f"/admin/product-types/{clothing.id}/edit",
        "/admin/products",
        "/admin/products/new",
        f"/admin/products/{shirt.id}/edit",
        "/admin/inventory",
        f"/admin/orders/{order.id}",
    ):
        assert client.get(url).status_code == 200, url
    assert b"size-editor-data" in client.get(f"/admin/products/{shirt.id}/edit").data


def test_admin_adds_custom_sizes_on_product(client, admin_user, category, clothing):
    admin_login(client, admin_user.email)
    data = {
        "category_id": category.id,
        "subcategory_id": 0,
        "product_type_id": clothing.id,
        "name": "Big Tee",
        "sku": "tee-big",
        "price": "599.00",
        "low_stock_threshold": 1,
        "is_active": "y",
        "size_custom": ["XXL", "3XL", "m"],  # "m" duplicates the type's M
        "size_on": ["M", "L", "XXL", "3XL"],
        "size_stock__M": "2",
        "size_stock__L": "3",
        "size_stock__XXL": "4",
        "size_stock__3XL": "1",
    }
    client.post("/admin/products/new", data=data, follow_redirects=True)
    product = Product.first(Product.sku == "TEE-BIG")
    assert [(s.name, s.stock_quantity) for s in product.sizes] == [("M", 2), ("L", 3), ("XXL", 4), ("3XL", 1)]
    assert product.stock_quantity == 10

    # Editing keeps the hand-added sizes on offer without re-adding them.
    data.update({"size_custom": [], "size_on": ["M", "3XL"], "size_stock__3XL": "7"})
    client.post(f"/admin/products/{product.id}/edit", data=data, follow_redirects=True)
    product = reload(product)
    assert [(s.name, s.stock_quantity) for s in product.sizes] == [("M", 2), ("3XL", 7)]


def test_custom_sizes_without_type(client, admin_user, category):
    admin_login(client, admin_user.email)
    client.post(
        "/admin/products/new",
        data={
            "category_id": category.id,
            "subcategory_id": 0,
            "product_type_id": 0,
            "name": "Poster",
            "sku": "poster-1",
            "price": "199.00",
            "low_stock_threshold": 1,
            "is_active": "y",
            "size_custom": ["A4", "A3"],
            "size_on": ["A4", "A3"],
            "size_stock__A4": "5",
            "size_stock__A3": "2",
        },
        follow_redirects=True,
    )
    product = Product.first(Product.sku == "POSTER-1")
    assert product.size_names == ["A4", "A3"]
    assert product.display_size_label == "Size"
    assert product.stock_quantity == 7


def test_product_page_has_zoom_viewer(client, shirt):
    shirt.image_url = "https://example.com/a.png"
    shirt.put()
    resp = client.get(f"/product/{shirt.slug}")
    assert b"imageLightbox" in resp.data
    assert b"data-zoom-open" in resp.data
