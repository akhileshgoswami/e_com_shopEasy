from app.models import Order, OrderStatus, PaymentStatus
from app.services.order_service import OrderService, PaymentCollectionError
from tests.conftest import admin_login, login


def _place_cod_order(client, customer, product, address):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    client.post("/checkout/place", data={"address_id": address.id, "payment_method": "cod"})
    return Order.query.filter_by(user_id=customer.id).first()


def test_admin_can_collect_cod_payment(client, admin_user, customer, product, address, db):
    order = _place_cod_order(client, customer, product, address)
    assert order.payment_status == PaymentStatus.PENDING

    client.get("/logout")
    admin_login(client, admin_user.email)
    resp = client.post(f"/admin/orders/{order.id}/collect-payment", follow_redirects=True)
    assert resp.status_code == 200

    db.session.refresh(order)
    assert order.payment_status == PaymentStatus.PAID


def test_collect_payment_button_hidden_once_paid(client, admin_user, customer, product, address, db):
    order = _place_cod_order(client, customer, product, address)
    client.get("/logout")
    admin_login(client, admin_user.email)
    client.post(f"/admin/orders/{order.id}/collect-payment")

    resp = client.get(f"/admin/orders/{order.id}")
    assert b"Mark payment as collected" not in resp.data


def test_collect_payment_rejected_for_razorpay_orders(app, admin_user, customer, product, address, db):
    from app.cart.services import CartService
    from app.checkout.services import CheckoutService

    CartService.add_item(customer, product.id, 1)
    order = CheckoutService.create_order(customer, address, "razorpay")
    try:
        OrderService.mark_cod_payment_collected(order, changed_by=admin_user.email)
        assert False, "expected PaymentCollectionError"
    except PaymentCollectionError as exc:
        assert "Cash on Delivery" in str(exc)


def test_collect_payment_rejected_for_cancelled_order(client, admin_user, customer, product, address, db):
    order = _place_cod_order(client, customer, product, address)
    client.get("/logout")
    admin_login(client, admin_user.email)
    client.post(f"/admin/orders/{order.id}/status", data={"new_status": "cancelled", "note": "test"})

    db.session.refresh(order)
    assert order.order_status == OrderStatus.CANCELLED

    resp = client.post(f"/admin/orders/{order.id}/collect-payment", follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(order)
    assert order.payment_status != PaymentStatus.PAID


def test_collect_payment_survives_full_delivery_flow(client, admin_user, customer, product, address, db):
    order = _place_cod_order(client, customer, product, address)
    client.get("/logout")
    admin_login(client, admin_user.email)

    for status in ["confirmed", "processing", "packed", "shipped", "delivered"]:
        resp = client.post(f"/admin/orders/{order.id}/status", data={"new_status": status, "note": ""}, follow_redirects=True)
        assert resp.status_code == 200

    db.session.refresh(order)
    assert order.order_status == OrderStatus.DELIVERED
    assert order.payment_status == PaymentStatus.PENDING

    resp = client.post(f"/admin/orders/{order.id}/collect-payment", follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(order)
    assert order.payment_status == PaymentStatus.PAID
    assert order.order_status == OrderStatus.DELIVERED  # unchanged
