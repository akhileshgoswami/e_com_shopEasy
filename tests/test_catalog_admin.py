from app.models import Category, Product, Subcategory
from tests.conftest import admin_login, reload


def test_category_crud(client, admin_user):
    admin_login(client, admin_user.email)

    resp = client.post(
        "/admin/categories/new",
        data={"name": "Fashion", "description": "Clothes", "sort_order": 0, "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    category = Category.first(Category.name == "Fashion")
    assert category is not None
    assert category.slug == "fashion"

    resp = client.post(
        f"/admin/categories/{category.id}/edit",
        data={"name": "Fashion & Style", "description": "Updated", "sort_order": 1, "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    category = reload(category)
    assert category.name == "Fashion & Style"

    resp = client.post(f"/admin/categories/{category.id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    category = reload(category)
    assert category.is_active is False


def test_subcategory_crud(client, admin_user, category):
    admin_login(client, admin_user.email)

    resp = client.post(
        "/admin/subcategories/new",
        data={"category_id": category.id, "name": "Laptops", "description": "", "sort_order": 0, "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    sub = Subcategory.first(Subcategory.name == "Laptops")
    assert sub is not None
    assert sub.category_id == category.id

    resp = client.post(f"/admin/subcategories/{sub.id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    sub = reload(sub)
    assert sub.is_active is False


def test_product_crud(client, admin_user, category, subcategory):
    admin_login(client, admin_user.email)

    resp = client.post(
        "/admin/products/new",
        data={
            "category_id": category.id,
            "subcategory_id": subcategory.id,
            "name": "New Gadget",
            "sku": "SKU-NEW-001",
            "short_description": "A gadget",
            "description": "Full description",
            "price": "499.00",
            "sale_price": "",
            "stock_quantity": 20,
            "low_stock_threshold": 3,
            "is_active": "y",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    product = Product.first(Product.sku == "SKU-NEW-001")
    assert product is not None
    assert product.slug == "new-gadget"

    resp = client.post(
        f"/admin/products/{product.id}/edit",
        data={
            "category_id": category.id,
            "subcategory_id": subcategory.id,
            "name": "New Gadget",
            "sku": "SKU-NEW-001",
            "short_description": "A gadget",
            "description": "Full description",
            "price": "599.00",
            "sale_price": "499.00",
            "stock_quantity": 15,
            "low_stock_threshold": 3,
            "is_active": "y",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    product = reload(product)
    assert float(product.price) == 599.00
    assert float(product.sale_price) == 499.00

    resp = client.post(f"/admin/products/{product.id}/toggle-active", follow_redirects=True)
    assert resp.status_code == 200
    product = reload(product)
    assert product.is_active is False


def test_duplicate_sku_rejected(client, admin_user, category, product):
    admin_login(client, admin_user.email)
    resp = client.post(
        "/admin/products/new",
        data={
            "category_id": category.id,
            "subcategory_id": 0,
            "name": "Duplicate SKU Product",
            "sku": product.sku,
            "short_description": "",
            "description": "",
            "price": "100.00",
            "sale_price": "",
            "stock_quantity": 5,
            "low_stock_threshold": 2,
            "is_active": "y",
        },
        follow_redirects=True,
    )
    assert b"already in use" in resp.data


def test_product_search(client, product):
    resp = client.get(f"/search?q={product.name.split()[0]}")
    assert resp.status_code == 200
    assert product.name.encode() in resp.data


def test_customer_cannot_access_admin_crud(client, customer, category):
    from tests.conftest import login

    login(client, customer.email)
    resp = client.get("/admin/categories")
    assert resp.status_code == 403
    resp = client.post("/admin/categories/new", data={"name": "Hack", "sort_order": 0})
    assert resp.status_code == 403
