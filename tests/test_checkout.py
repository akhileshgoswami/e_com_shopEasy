from app.checkout.services import CheckoutError, CheckoutService
from app.models import Order, OrderStatus, PaymentStatus
from tests.conftest import login, reload


def test_checkout_cod_creates_order_and_reserves_stock(client, customer, product, address):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 3})

    initial_stock = product.stock_quantity

    resp = client.post(
        "/checkout/place",
        data={"address_id": address.id, "payment_method": "cod"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    order = Order.first(Order.user_id == customer.id)
    assert order is not None
    assert order.payment_method == "cod"
    assert order.order_status == OrderStatus.PLACED
    assert order.payment_status == PaymentStatus.PENDING
    assert order.stock_committed is True
    assert len(order.items) == 1
    assert order.items[0].quantity == 3

    product = reload(product)
    assert product.stock_quantity == initial_stock - 3


def test_checkout_rejects_empty_cart(app, customer, address):
    with app.test_request_context():
        pass
    try:
        CheckoutService.create_order(customer, address, "cod")
        assert False, "expected CheckoutError"
    except CheckoutError as exc:
        assert "empty" in str(exc).lower()


def test_checkout_clamps_quantity_when_stock_drops_before_checkout(client, customer, product, address):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": product.stock_quantity})

    # Simulate a race: another process drops stock to 1 right before checkout.
    # CartService.sync_cart() runs at the start of checkout and clamps the
    # cart line to what's actually available instead of hard-failing.
    product.stock_quantity = 1
    product.put()

    resp = client.post(
        "/checkout/place",
        data={"address_id": address.id, "payment_method": "cod"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    order = Order.first(Order.user_id == customer.id)
    assert order is not None
    assert order.items[0].quantity == 1
    product = reload(product)
    assert product.stock_quantity == 0


def test_inventory_service_rejects_reservation_over_available_stock(app, product):
    from app.services.inventory_service import InsufficientStockError, InventoryService

    original_stock = product.stock_quantity
    try:
        InventoryService.reserve_stock(product.id, original_stock + 1)
        assert False, "expected InsufficientStockError"
    except InsufficientStockError:
        pass

    product = reload(product)
    assert product.stock_quantity == original_stock  # unchanged, no partial mutation leaked


def test_order_detail_blocks_other_users(client, customer, other_customer, product, address):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    client.post("/checkout/place", data={"address_id": address.id, "payment_method": "cod"})
    order = Order.first(Order.user_id == customer.id)

    client.get("/logout")
    login(client, other_customer.email)
    resp = client.get(f"/orders/{order.id}")
    assert resp.status_code == 404


def test_admin_order_status_transition_restores_stock_on_cancel(client, admin_user, customer, product, address):
    login_resp = client.post(
        "/login", data={"email": customer.email, "password": "Passw0rd!"}, follow_redirects=True
    )
    client.post("/cart/add", data={"product_id": product.id, "quantity": 2})
    client.post("/checkout/place", data={"address_id": address.id, "payment_method": "cod"})
    order = Order.first(Order.user_id == customer.id)
    stock_after_order = reload(product).stock_quantity

    client.get("/logout")
    from tests.conftest import admin_login

    admin_login(client, admin_user.email)
    resp = client.post(
        f"/admin/orders/{order.id}/status",
        data={"new_status": "cancelled", "note": "Customer requested cancellation"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    order = reload(order)
    product = reload(product)
    assert order.order_status == OrderStatus.CANCELLED
    assert order.stock_committed is False
    assert product.stock_quantity == stock_after_order + 2


def test_invalid_status_transition_rejected(client, admin_user, customer, product, address):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    client.post("/checkout/place", data={"address_id": address.id, "payment_method": "cod"})
    order = Order.first(Order.user_id == customer.id)

    client.get("/logout")
    from tests.conftest import admin_login

    admin_login(client, admin_user.email)
    # placed -> delivered is not a direct allowed transition
    resp = client.post(
        f"/admin/orders/{order.id}/status",
        data={"new_status": "delivered", "note": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    order = reload(order)
    assert order.order_status == OrderStatus.PLACED
