import pytest
from flask import g

from app.services.email_template_service import EMAIL_TEMPLATES, EmailTemplateService, fill
from tests.conftest import admin_login, login, messages_to
from tests.test_order_emails import place_cod_order

DEFAULT_FORM = EMAIL_TEMPLATES["order_confirmation"]["defaults"]


def edit(client, key="order_confirmation", action="save", **fields):
    data = {**EMAIL_TEMPLATES[key]["defaults"], **fields, "action": action}
    return client.post(f"/admin/emails/{key}", data=data, follow_redirects=True)


@pytest.fixture()
def admin_client(client, admin_user):
    admin_login(client, admin_user.email)
    return client


def test_list_shows_every_email(admin_client):
    html = admin_client.get("/admin/emails").get_data(as_text=True)
    for spec in EMAIL_TEMPLATES.values():
        assert spec["name"] in html
    assert "Email templates" in admin_client.get("/admin/dashboard").get_data(as_text=True)


@pytest.mark.parametrize("key", list(EMAIL_TEMPLATES))
def test_every_template_previews(admin_client, key):
    resp = admin_client.get(f"/admin/emails/{key}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "srcdoc=" in html and 'sandbox=""' in html
    assert "{customer_name}" not in EmailTemplateService.preview(key)[1]


def test_unknown_template_is_404(admin_client):
    assert admin_client.get("/admin/emails/nope").status_code == 404


def test_customers_and_visitors_cannot_edit(app, client, customer):
    login(client, customer.email)
    assert client.get("/admin/emails").status_code == 403
    assert edit(client, subject="Hacked").status_code == 403
    g.pop("_login_user", None)
    anonymous = app.test_client()
    assert anonymous.get("/admin/emails").status_code == 302
    assert EmailTemplateService.overrides("order_confirmation") == {}


def test_saved_wording_is_used_in_real_emails(admin_client, client, customer, product, address, mail_outbox, admin_user):
    resp = edit(
        admin_client,
        subject="Yay! Order {order_number} is in",
        heading="Thank you, {customer_name}",
        intro="We're packing it with care.\n\nTotal: {order_total}",
        button_label="Track my order",
        note="Use code BACK10 for 10% off next time.",
    )
    assert b"email saved" in resp.data
    assert "customized" in admin_client.get("/admin/emails").get_data(as_text=True)

    client.get("/logout")
    g.pop("_login_user", None)
    order = place_cod_order(client, customer, product, address)
    message = messages_to(mail_outbox, customer.email)[0]
    assert message.subject == f"Yay! Order {order.order_number} is in"
    for body in (message.html, message.body):
        assert "Thank you, Test User" in body
        assert "We're packing it with care." in body or "We&#39;re packing it with care." in body
        assert "Total: ₹1,000.00" in body
        assert "Track my order" in body
        assert "BACK10" in body
        # Structural parts stay.
        assert order.order_number in body and "Test Phone" in body


def test_unknown_placeholder_is_rejected(admin_client):
    resp = edit(admin_client, subject="Order {order_id}")
    assert b"Unknown placeholder: {order_id}" in resp.data
    assert EmailTemplateService.overrides("order_confirmation") == {}


def test_admin_input_is_escaped_and_not_evaluated(admin_client, customer, product, address, client, mail_outbox):
    edit(admin_client, intro="<b>bold</b> {{ config.SECRET_KEY }} {order.__class__}")
    copy = EmailTemplateService.resolve("order_confirmation", {"order_number": "X"})
    assert "{{ config.SECRET_KEY }}" in copy["intro"]  # plain text, not a template
    subject, html, text = EmailTemplateService.preview("order_confirmation")
    assert "&lt;b&gt;bold&lt;/b&gt;" in html
    assert "test-secret-key" not in html + text
    assert "{order.__class__}" in fill("{order.__class__}", {"order": object()})


def test_preview_does_not_save(admin_client):
    resp = edit(admin_client, action="preview", heading="Draft heading")
    assert b"unsaved preview" in resp.data
    assert b"Draft heading" in resp.data
    assert EmailTemplateService.overrides("order_confirmation") == {}


def test_send_test_to_admin(admin_client, admin_user, mail_outbox):
    resp = edit(admin_client, action="test", heading="Testing 123")
    assert b"Test email sent to admin@example.com" in resp.data
    assert len(mail_outbox) == 1
    assert mail_outbox[0].recipients == [admin_user.email]
    assert mail_outbox[0].subject.startswith("[Test] Order Confirmed")
    assert "Testing 123" in mail_outbox[0].html
    assert EmailTemplateService.overrides("order_confirmation") == {}


def test_reset_and_default_values_are_not_stored(admin_client):
    edit(admin_client)  # saving defaults stores nothing
    assert EmailTemplateService.overrides("order_confirmation") == {}
    edit(admin_client, heading="Custom")
    assert EmailTemplateService.overrides("order_confirmation") == {"heading": "Custom"}
    admin_client.post("/admin/emails/order_confirmation/reset")
    assert EmailTemplateService.overrides("order_confirmation") == {}


def test_status_email_wording_is_editable(admin_client, client, customer, product, address, mail_outbox):
    edit(admin_client, key="order_status_updated", subject="{new_status}: #{order_number}", intro="Was {old_status}.")
    from app.services.order_service import OrderService

    client.get("/logout")
    g.pop("_login_user", None)
    order = place_cod_order(client, customer, product, address)
    mail_outbox.clear()
    OrderService.change_status(order, "confirmed", changed_by="admin@example.com")
    assert mail_outbox[0].subject == f"Confirmed: #{order.order_number}"
    assert "Was Placed." in mail_outbox[0].body
    # Default heading still comes from the status.
    assert "Your order has been confirmed." in mail_outbox[0].html


def test_reset_email_keeps_link_and_warning_whatever_the_wording(admin_client, customer, mail_outbox):
    edit(admin_client, key="forgot_password", intro="Short.", button_label="Go")
    admin_client.get("/logout")
    g.pop("_login_user", None)
    admin_client.post("/forgot-password", data={"email": customer.email})
    message = messages_to(mail_outbox, customer.email)[0]
    assert "https://shop.example.com/reset-password/" in message.html
    assert "30 minutes" in message.html and "ignore this email" in message.html
    assert ">Go</a>" in message.html
