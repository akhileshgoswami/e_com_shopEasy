from app.models import CartItem
from tests.conftest import login


def test_add_to_cart_requires_login(client, product):
    resp = client.post("/cart/add", data={"product_id": product.id, "quantity": 1}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_add_to_cart_preserves_intent_after_login(client, customer, product):
    client.post("/cart/add", data={"product_id": product.id, "quantity": 2})
    login(client, customer.email)
    item = CartItem.query.filter_by(product_id=product.id).first()
    assert item is not None
    assert item.quantity == 2


def test_add_to_cart_success(client, customer, product):
    login(client, customer.email)
    resp = client.post("/cart/add", data={"product_id": product.id, "quantity": 3}, follow_redirects=True)
    assert resp.status_code == 200
    item = CartItem.query.filter_by(product_id=product.id).first()
    assert item.quantity == 3
    assert float(item.unit_price) == float(product.price)


def test_cart_rejects_quantity_over_stock(client, customer, product):
    login(client, customer.email)
    resp = client.post("/cart/add", data={"product_id": product.id, "quantity": 999}, follow_redirects=True)
    assert b"available" in resp.data


def test_cart_update_quantity(client, customer, product, db):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    item = CartItem.query.filter_by(product_id=product.id).first()
    resp = client.post(f"/cart/update/{item.id}", data={"quantity": 5}, follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(item)
    assert item.quantity == 5


def test_cart_remove_item(client, customer, product):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    item = CartItem.query.filter_by(product_id=product.id).first()
    resp = client.post(f"/cart/remove/{item.id}", follow_redirects=True)
    assert resp.status_code == 200
    assert CartItem.query.filter_by(id=item.id).first() is None


def test_cart_isolated_per_user(client, customer, other_customer, product, db):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    my_item = CartItem.query.filter_by(product_id=product.id).first()

    client.get("/logout")
    login(client, other_customer.email)

    resp = client.post(f"/cart/update/{my_item.id}", data={"quantity": 2}, follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(my_item)
    assert my_item.quantity == 1  # unchanged: belongs to a different user's cart
