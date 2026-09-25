import json
import logging
import smtplib
import ssl
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from flask import g

from app.models import EmailOutbox, EmailStatus, Order, OrderStatus, PaymentStatus
from app.services.email_service import EmailService, _VerifiedSMTPConnection
from tests.conftest import admin_login, login, messages_to, reload
from tests.test_payments import _create_razorpay_order, _fake_create_order

OWNER = "owner@example.com"


def place_cod_order(client, customer, product, address, quantity=1):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": quantity})
    client.post("/checkout/place", data={"address_id": address.id, "payment_method": "cod"})
    return Order.first(Order.user_id == customer.id)


def switch_to_admin(client, admin_user):
    client.get("/logout")
    g.pop("_login_user", None)
    admin_login(client, admin_user.email)


def set_status(client, order, status, **extra):
    return client.post(f"/admin/orders/{order.id}/status", data={"new_status": status, "note": "", **extra})


def subjects(messages):
    return [m.subject for m in messages]


# ---------------------------------------------------------------------------
# New orders
# ---------------------------------------------------------------------------


def test_cod_order_sends_customer_and_owner_emails(client, customer, product, address, mail_outbox):
    order = place_cod_order(client, customer, product, address, quantity=2)

    customer_mail = messages_to(mail_outbox, customer.email)
    owner_mail = messages_to(mail_outbox, OWNER)
    assert subjects(customer_mail) == [f"Order Confirmed — #{order.order_number}"]
    assert subjects(owner_mail) == [f"New Order Received — #{order.order_number}"]

    confirmation = customer_mail[0]
    for text in (confirmation.html, confirmation.body):
        assert order.order_number in text
        assert "Test Phone" in text
        assert "Cash on Delivery" in text
        assert "Pay on delivery" in text
        assert "2000.00" in text
        assert "123 Main St" in text
    assert f"https://shop.example.com/orders/{order.id}" in confirmation.html
    # Admin-only details never reach the customer.
    assert "/admin/" not in confirmation.html + confirmation.body

    alert = owner_mail[0]
    assert f"https://shop.example.com/admin/orders/{order.id}" in alert.html
    assert customer.email in alert.html and "9999999999" in alert.html
    assert "SKU-TEST-001" in alert.body
    assert alert.reply_to == customer.email


def test_owner_email_supports_several_recipients(app, client, customer, product, address, mail_outbox):
    app.config["OWNER_EMAIL"] = "a@example.com; b@example.com"
    place_cod_order(client, customer, product, address)
    owner_alert = [m for m in mail_outbox if "New Order" in m.subject]
    assert len(owner_alert) == 1
    assert owner_alert[0].recipients == ["a@example.com", "b@example.com"]


def test_missing_owner_email_logs_error_and_still_confirms_to_customer(app, client, customer, product, address, mail_outbox, caplog):
    app.config["OWNER_EMAIL"] = ""
    logging.getLogger("app").propagate = True
    try:
        with caplog.at_level(logging.ERROR, logger="app.email"):
            order = place_cod_order(client, customer, product, address)
    finally:
        logging.getLogger("app").propagate = False
    assert subjects(mail_outbox) == [f"Order Confirmed — #{order.order_number}"]
    assert "OWNER_EMAIL is not configured" in caplog.text


def test_user_content_is_escaped_in_html(client, customer, product, address, mail_outbox):
    address.full_name = "<script>alert(1)</script>"
    address.put()
    place_cod_order(client, customer, product, address)
    for message in mail_outbox:
        assert "<script>alert(1)</script>" not in message.html
        assert "&lt;script&gt;" in message.html


def test_razorpay_order_emails_only_after_verified_payment(client, customer, product, address, mail_outbox):
    order = _create_razorpay_order(client, customer, product, address)
    assert mail_outbox == []

    with patch("app.payments.routes.RazorpayService.create_order", side_effect=_fake_create_order()):
        client.post("/payment/razorpay/create-order", json={"order_id": order.id})
    assert mail_outbox == []

    with patch("app.payments.routes.RazorpayService.verify_payment_signature", return_value=True):
        payload = {
            "order_id": order.id,
            "razorpay_order_id": "order_fake123",
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "sig",
        }
        assert client.post("/payment/razorpay/verify", json=payload).get_json()["success"]
        # The browser retries the callback.
        client.post("/payment/razorpay/verify", json=payload)

    order = reload(order)
    assert order.payment_status == PaymentStatus.PAID
    assert order.order_status == OrderStatus.PLACED
    customer_mail = messages_to(mail_outbox, customer.email)
    assert subjects(customer_mail) == [f"Order Confirmed — #{order.order_number}"]
    assert "Paid (verified)" in customer_mail[0].html
    assert "Online payment (Razorpay)" in customer_mail[0].body
    assert len(messages_to(mail_outbox, OWNER)) == 1


@patch("app.payments.webhook.RazorpayService.verify_webhook_signature", return_value=True)
def test_webhook_racing_the_browser_callback_does_not_duplicate(mock_verify, client, customer, product, address, mail_outbox):
    order = _create_razorpay_order(client, customer, product, address)
    order.razorpay_order_id = "order_race"
    order.put()

    with patch("app.payments.routes.RazorpayService.verify_payment_signature", return_value=True):
        client.post(
            "/payment/razorpay/verify",
            json={"order_id": order.id, "razorpay_order_id": "order_race", "razorpay_payment_id": "pay_r", "razorpay_signature": "s"},
        )
    for event_id in ("evt_a", "evt_b"):
        client.post(
            "/webhooks/razorpay",
            data=json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_r", "order_id": "order_race"}}}}),
            content_type="application/json",
            headers={"X-Razorpay-Signature": "sig", "X-Razorpay-Event-Id": event_id},
        )

    assert len(messages_to(mail_outbox, customer.email)) == 1
    assert len(messages_to(mail_outbox, OWNER)) == 1


def test_failed_razorpay_payment_sends_nothing(client, customer, product, address, mail_outbox):
    order = _create_razorpay_order(client, customer, product, address)
    client.post("/payment/razorpay/failed", json={"order_id": order.id, "reason": "Card declined"})

    order.razorpay_order_id = "order_bad"
    order.put()
    from app.payments.razorpay_service import RazorpayError

    with patch("app.payments.routes.RazorpayService.verify_payment_signature", side_effect=RazorpayError("bad signature")):
        resp = client.post(
            "/payment/razorpay/verify",
            json={"order_id": order.id, "razorpay_order_id": "order_bad", "razorpay_payment_id": "pay_x", "razorpay_signature": "forged"},
        )
    assert resp.status_code == 400
    assert reload(order).payment_status == PaymentStatus.PENDING
    assert mail_outbox == []


# ---------------------------------------------------------------------------
# Status updates
# ---------------------------------------------------------------------------


def test_admin_status_change_emails_customer_with_tracking(client, admin_user, customer, product, address, mail_outbox):
    order = place_cod_order(client, customer, product, address)
    switch_to_admin(client, admin_user)
    mail_outbox.clear()

    for status in ("confirmed", "processing", "packed"):
        set_status(client, order, status)
    set_status(
        client,
        order,
        "shipped",
        tracking_number="AWB123456",
        tracking_url="https://courier.example/track/AWB123456",
        estimated_delivery_date="2026-10-01",
    )

    assert subjects(mail_outbox) == [
        f"Your order #{order.order_number} is confirmed",
        f"Your order #{order.order_number} is being prepared",
        f"Your order #{order.order_number} is packed",
        f"Your order #{order.order_number} has shipped",
    ]
    assert all(m.recipients == [customer.email] for m in mail_outbox)
    shipped = mail_outbox[-1]
    assert "Your order is on its way." in shipped.html
    assert "Packed" in shipped.html and "Shipped" in shipped.html
    assert "AWB123456" in shipped.html and "AWB123456" in shipped.body
    assert "https://courier.example/track/AWB123456" in shipped.html
    assert "Thu, 01 Oct 2026" in shipped.body
    assert "AWB123456" not in mail_outbox[0].html

    order = reload(order)
    assert order.tracking_number == "AWB123456"
    assert order.estimated_delivery_date == date(2026, 10, 1)


def test_out_for_delivery_and_delivered_emails(client, admin_user, customer, product, address, mail_outbox):
    order = place_cod_order(client, customer, product, address)
    order.order_status = OrderStatus.SHIPPED
    order.put()
    switch_to_admin(client, admin_user)
    mail_outbox.clear()

    set_status(client, order, "out_for_delivery")
    set_status(client, order, "delivered")

    assert subjects(mail_outbox) == [
        f"Your order #{order.order_number} is out for delivery",
        f"Your order #{order.order_number} has been delivered",
    ]
    assert "expected to arrive soon" in mail_outbox[0].html
    assert "Your order has been delivered" in mail_outbox[1].html


def test_cancellation_uses_cancelled_template(client, admin_user, customer, product, address, mail_outbox):
    order = place_cod_order(client, customer, product, address)
    switch_to_admin(client, admin_user)
    mail_outbox.clear()
    set_status(client, order, "cancelled", cancel_reason="Item out of stock")
    assert subjects(mail_outbox) == [f"Your order #{order.order_number} has been cancelled"]
    assert "Your order has been cancelled" in mail_outbox[0].html


def test_repeated_or_invalid_status_requests_send_no_extra_email(client, admin_user, customer, product, address, mail_outbox):
    order = place_cod_order(client, customer, product, address)
    switch_to_admin(client, admin_user)
    mail_outbox.clear()

    set_status(client, order, "confirmed")
    set_status(client, order, "confirmed")  # double-submitted form
    set_status(client, order, "delivered")  # not an allowed transition
    assert len(mail_outbox) == 1
    assert reload(order).order_status == OrderStatus.CONFIRMED


def test_unchanged_status_sends_no_email(app, customer, product, address, client, mail_outbox):
    from app.services.order_service import OrderService

    order = place_cod_order(client, customer, product, address)
    mail_outbox.clear()
    OrderService.change_status(order, OrderStatus.PLACED, changed_by="admin@example.com")
    assert mail_outbox == []


def test_invalid_tracking_link_is_rejected(client, admin_user, customer, product, address, mail_outbox):
    order = place_cod_order(client, customer, product, address)
    order.order_status = OrderStatus.PACKED
    order.put()
    switch_to_admin(client, admin_user)
    mail_outbox.clear()

    resp = set_status(client, order, "shipped", tracking_url="javascript:alert(1)")
    assert resp.status_code == 302
    assert reload(order).order_status == OrderStatus.PACKED
    assert mail_outbox == []


def test_customer_cannot_trigger_admin_status_email(client, customer, product, address, mail_outbox):
    order = place_cod_order(client, customer, product, address)
    mail_outbox.clear()
    resp = set_status(client, order, "confirmed")
    assert resp.status_code == 403
    assert reload(order).order_status == OrderStatus.PLACED
    assert mail_outbox == []


def test_anonymous_user_cannot_trigger_admin_status_email(app, customer, product, address, client, mail_outbox):
    order = place_cod_order(client, customer, product, address)
    mail_outbox.clear()
    anonymous = app.test_client()
    g.pop("_login_user", None)
    resp = set_status(anonymous, order, "confirmed")
    assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]
    assert reload(order).order_status == OrderStatus.PLACED
    assert mail_outbox == []


def test_cod_payment_collected_email(client, admin_user, customer, product, address, mail_outbox):
    order = place_cod_order(client, customer, product, address)
    switch_to_admin(client, admin_user)
    mail_outbox.clear()
    client.post(f"/admin/orders/{order.id}/collect-payment")
    client.post(f"/admin/orders/{order.id}/collect-payment")
    assert subjects(mail_outbox) == [f"Payment received — #{order.order_number}"]


# ---------------------------------------------------------------------------
# Delivery failures, retries and transport security
# ---------------------------------------------------------------------------


def test_smtp_failure_never_breaks_checkout_and_is_retried(client, customer, product, address, mail_outbox):
    with patch.object(_VerifiedSMTPConnection, "send", side_effect=smtplib.SMTPServerDisconnected("down")):
        order = place_cod_order(client, customer, product, address)

    assert order is not None and order.order_status == OrderStatus.PLACED
    assert mail_outbox == []
    rows = EmailOutbox.all(EmailOutbox.status == EmailStatus.FAILED)
    assert {r.key_name for r in rows} == {f"order_confirmation:{order.id}", f"owner_new_order:{order.id}"}
    assert all("SMTPServerDisconnected" in r.last_error for r in rows)

    sent, failed = EmailService.retry_pending()
    assert (sent, failed) == (2, 0)
    assert len(mail_outbox) == 2
    # Nothing left to retry, and a second run sends nothing.
    assert EmailService.retry_pending() == (0, 0)
    assert len(mail_outbox) == 2


def test_retry_cli_command(app, client, customer, product, address, mail_outbox):
    with patch.object(_VerifiedSMTPConnection, "send", side_effect=smtplib.SMTPException("boom")):
        place_cod_order(client, customer, product, address)
    result = app.test_cli_runner().invoke(args=["send-pending-emails"])
    assert "2 sent, 0 failed" in result.output
    assert len(mail_outbox) == 2


def test_emails_are_not_sent_when_mail_disabled(app, client, customer, product, address):
    from app.extensions import mail

    app.config["MAIL_ENABLED"] = False
    with mail.record_messages() as outbox:
        place_cod_order(client, customer, product, address)
    assert outbox == []
    assert EmailOutbox.all() == []


def test_smtp_connection_verifies_certificates_and_times_out(app):
    state = app.extensions["mail"]
    connection = _VerifiedSMTPConnection(state)
    with patch.object(state, "server", "smtp.example.com"), patch.object(state, "port", 587), \
            patch.object(state, "use_tls", True), patch.object(state, "use_ssl", False), \
            patch.object(state, "username", "user"), patch.object(state, "password", "secret"), \
            patch("app.services.email_service.smtplib.SMTP") as smtp:
        host = MagicMock()
        smtp.return_value = host
        connection.configure_host()

    smtp.assert_called_once_with("smtp.example.com", 587, timeout=app.config["MAIL_TIMEOUT_SECONDS"])
    context = host.starttls.call_args.kwargs["context"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    host.set_debuglevel.assert_called_once_with(0)
    host.login.assert_called_once_with("user", "secret")


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"MAIL_USE_TLS": True, "MAIL_USE_SSL": True}, "both true"),
        ({"MAIL_SERVER": None}, "MAIL_SERVER is not set"),
        ({"OWNER_EMAIL": ""}, "OWNER_EMAIL is not set"),
        ({"BASE_URL": "shop.example.com"}, "BASE_URL must be an absolute"),
    ],
)
def test_config_validation(app, overrides, expected):
    app.config.update({"MAIL_ENABLED": True, "MAIL_SERVER": "smtp.example.com", **overrides})
    problems = EmailService.validate_config(app)
    assert any(expected in p for p in problems)


def test_logs_mask_recipients_and_never_include_reset_links(client, customer, mail_outbox, caplog):
    logging.getLogger("app").propagate = True
    try:
        with caplog.at_level(logging.DEBUG):
            client.post("/forgot-password", data={"email": customer.email})
    finally:
        logging.getLogger("app").propagate = False
    token_url = mail_outbox[0].body.split("reset-password/")[1].split()[0]
    assert token_url not in caplog.text
    assert customer.email not in caplog.text
    assert "c***@example.com" in caplog.text
