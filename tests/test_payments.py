import json
from unittest.mock import patch

from app.models import Order, OrderStatus, Payment, PaymentStatus, WebhookEvent
from app.payments.razorpay_service import RazorpayError
from tests.conftest import login, reload


def _create_razorpay_order(client, customer, product, address):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    client.post("/checkout/place", data={"address_id": address.id, "payment_method": "razorpay"})
    order = Order.first(Order.user_id == customer.id)
    return order


def _fake_create_order(razorpay_order_id="order_fake123", amount_paise=100000):
    """Mimics RazorpayService.create_order's real side effect of persisting
    razorpay_order_id on the Order, which the verify endpoint depends on."""

    def _side_effect(order):
        order.razorpay_order_id = razorpay_order_id
        order.put()
        return {"razorpay_order_id": razorpay_order_id, "amount_paise": amount_paise, "currency": "INR"}

    return _side_effect


def test_razorpay_checkout_reserves_stock_pending_payment(client, customer, product, address):
    initial_stock = product.stock_quantity
    order = _create_razorpay_order(client, customer, product, address)

    assert order.order_status == OrderStatus.PENDING_PAYMENT
    assert order.payment_status == PaymentStatus.PENDING
    assert order.stock_committed is True

    product = reload(product)
    assert product.stock_quantity == initial_stock - 1


@patch("app.payments.routes.RazorpayService.create_order")
def test_create_razorpay_order_endpoint(mock_create_order, client, customer, product, address):
    order = _create_razorpay_order(client, customer, product, address)
    mock_create_order.side_effect = _fake_create_order()

    resp = client.post("/payment/razorpay/create-order", json={"order_id": order.id})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["razorpay_order_id"] == "order_fake123"


@patch("app.payments.routes.RazorpayService.verify_payment_signature")
@patch("app.payments.routes.RazorpayService.create_order")
def test_verify_payment_marks_order_paid(mock_create_order, mock_verify, client, customer, product, address):
    order = _create_razorpay_order(client, customer, product, address)
    mock_create_order.side_effect = _fake_create_order()
    client.post("/payment/razorpay/create-order", json={"order_id": order.id})

    mock_verify.return_value = True
    resp = client.post(
        "/payment/razorpay/verify",
        json={
            "order_id": order.id,
            "razorpay_order_id": "order_fake123",
            "razorpay_payment_id": "pay_fake123",
            "razorpay_signature": "sig_fake",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True

    order = reload(order)
    assert order.payment_status == PaymentStatus.PAID
    assert order.order_status == OrderStatus.PLACED
    assert order.razorpay_payment_id == "pay_fake123"

    payment = Payment.first(Payment.order_id == order.id, Payment.provider == "razorpay")
    assert payment.status == "paid"
    assert payment.signature_verified is True


@patch("app.payments.routes.RazorpayService.verify_payment_signature")
@patch("app.payments.routes.RazorpayService.create_order")
def test_verify_payment_signature_failure(mock_create_order, mock_verify, client, customer, product, address):
    order = _create_razorpay_order(client, customer, product, address)
    mock_create_order.side_effect = _fake_create_order()
    client.post("/payment/razorpay/create-order", json={"order_id": order.id})

    mock_verify.side_effect = RazorpayError("Payment signature verification failed.")
    resp = client.post(
        "/payment/razorpay/verify",
        json={
            "order_id": order.id,
            "razorpay_order_id": "order_fake123",
            "razorpay_payment_id": "pay_bad",
            "razorpay_signature": "bad_sig",
        },
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False

    order = reload(order)
    assert order.payment_status != PaymentStatus.PAID


def test_payment_failure_restores_stock(client, customer, product, address):
    initial_stock = product.stock_quantity
    order = _create_razorpay_order(client, customer, product, address)
    product = reload(product)
    assert product.stock_quantity == initial_stock - 1

    resp = client.post("/payment/razorpay/failed", json={"order_id": order.id, "reason": "User cancelled"})
    assert resp.status_code == 200

    order = reload(order)
    product = reload(product)
    assert order.order_status == OrderStatus.FAILED
    assert order.stock_committed is False
    assert product.stock_quantity == initial_stock  # restored


def test_payment_failure_reason_visible_in_admin(client, admin_user, customer, product, address):
    order = _create_razorpay_order(client, customer, product, address)
    client.post(
        "/payment/razorpay/failed",
        json={"order_id": order.id, "reason": "BAD_REQUEST_ERROR: International cards are not supported"},
    )

    payment = Payment.first(Payment.order_id == order.id, Payment.provider == "razorpay")
    assert payment.status == "failed"
    assert "International cards are not supported" in payment.raw_reference

    client.get("/logout")
    from tests.conftest import admin_login

    admin_login(client, admin_user.email)

    resp = client.get(f"/admin/orders/{order.id}")
    assert b"International cards are not supported" in resp.data

    resp = client.get("/admin/payments")
    assert b"International cards are not supported" in resp.data


@patch("app.payments.webhook.RazorpayService.verify_webhook_signature")
def test_webhook_marks_order_paid(mock_verify, client, customer, product, address):
    order = _create_razorpay_order(client, customer, product, address)
    order.razorpay_order_id = "order_webhook_1"
    order.put()

    mock_verify.return_value = True
    payload = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_webhook_1", "order_id": "order_webhook_1"}}},
    }
    resp = client.post(
        "/webhooks/razorpay",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"X-Razorpay-Signature": "sig", "X-Razorpay-Event-Id": "evt_1"},
    )
    assert resp.status_code == 200

    order = reload(order)
    assert order.payment_status == PaymentStatus.PAID
    assert WebhookEvent.get_by_id("evt_1") is not None


@patch("app.payments.webhook.RazorpayService.verify_webhook_signature")
def test_webhook_duplicate_event_is_idempotent(mock_verify, client, customer, product, address):
    order = _create_razorpay_order(client, customer, product, address)
    order.razorpay_order_id = "order_webhook_2"
    order.put()

    mock_verify.return_value = True
    payload = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_webhook_2", "order_id": "order_webhook_2"}}},
    }
    headers = {"X-Razorpay-Signature": "sig", "X-Razorpay-Event-Id": "evt_dup"}

    resp1 = client.post("/webhooks/razorpay", data=json.dumps(payload), content_type="application/json", headers=headers)
    resp2 = client.post("/webhooks/razorpay", data=json.dumps(payload), content_type="application/json", headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert WebhookEvent.query().count() == 1

    order = reload(order)
    assert order.payment_status == PaymentStatus.PAID


@patch("app.payments.webhook.RazorpayService.verify_webhook_signature")
def test_webhook_invalid_signature_rejected(mock_verify, client):
    mock_verify.side_effect = RazorpayError("bad signature")
    resp = client.post(
        "/webhooks/razorpay",
        data=json.dumps({"event": "payment.captured", "payload": {}}),
        content_type="application/json",
        headers={"X-Razorpay-Signature": "invalid"},
    )
    assert resp.status_code == 400
