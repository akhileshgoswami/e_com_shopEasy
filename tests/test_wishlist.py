from app.models import Wishlist
from tests.conftest import login, reload

AJAX = {"X-Requested-With": "XMLHttpRequest"}


def _saved_ids(user):
    wishlist = Wishlist.get_by_id(user.id)
    return list(wishlist.product_ids) if wishlist else []


def test_wishlist_page_requires_login(client):
    resp = client.get("/wishlist")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_toggle_adds_then_removes(client, customer, product):
    login(client, customer.email)

    resp = client.post("/wishlist/toggle", data={"product_id": product.id}, headers=AJAX)
    data = resp.get_json()
    assert data["success"] is True and data["in_wishlist"] is True and data["count"] == 1
    assert _saved_ids(customer) == [product.id]

    resp = client.post("/wishlist/toggle", data={"product_id": product.id}, headers=AJAX)
    data = resp.get_json()
    assert data["in_wishlist"] is False and data["count"] == 0
    assert _saved_ids(customer) == []


def test_wishlist_page_lists_saved_products(client, customer, product):
    login(client, customer.email)
    client.post("/wishlist/toggle", data={"product_id": product.id})

    html = client.get("/wishlist").get_data(as_text=True)
    assert product.name in html
    assert "bi-heart-fill" in html  # heart shows as saved


def test_inactive_products_are_hidden_and_cannot_be_saved(client, customer, product):
    login(client, customer.email)
    client.post("/wishlist/toggle", data={"product_id": product.id})
    product.is_active = False
    product.put()

    assert product.name not in client.get("/wishlist").get_data(as_text=True)

    other = reload(product)
    resp = client.post("/wishlist/toggle", data={"product_id": other.id}, headers=AJAX)
    assert resp.status_code == 400


def test_guest_heart_is_saved_after_login(client, customer, product):
    resp = client.post("/wishlist/toggle", data={"product_id": product.id}, headers=AJAX)
    assert resp.status_code == 401 and resp.get_json()["auth_required"] is True

    login(client, customer.email)
    assert _saved_ids(customer) == [product.id]


def test_wishlists_are_per_user(client, customer, other_customer, product):
    login(client, customer.email)
    client.post("/wishlist/toggle", data={"product_id": product.id})
    client.get("/logout")

    login(client, other_customer.email)
    assert product.name not in client.get("/wishlist").get_data(as_text=True)
    assert _saved_ids(other_customer) == []


def test_header_shows_wishlist_count(client, customer, product):
    login(client, customer.email)
    client.post("/wishlist/toggle", data={"product_id": product.id})
    html = client.get("/").get_data(as_text=True)
    assert 'aria-label="Wishlist"' in html
    assert "wishlist-badge-count" in html
