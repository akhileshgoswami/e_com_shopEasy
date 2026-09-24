from datetime import datetime, timezone

from app.models import Order, OrderStatus
from app.utils import to_ist
from tests.conftest import admin_login, login, reload


def _place_cod_order(client, customer, product, address, quantity=1):
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": quantity})
    client.post("/checkout/place", data={"address_id": address.id, "payment_method": "cod"})
    return Order.first(Order.user_id == customer.id)


def _last_note(order):
    return order.status_history[-1].note


def test_to_ist_shifts_utc_by_five_thirty():
    shown = to_ist(datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc))
    assert (shown.day, shown.hour, shown.minute) == (2, 1, 30)
    # naive values are treated as UTC
    assert to_ist(datetime(2026, 1, 1, 20, 0)).hour == 1


def test_order_page_shows_ist(client, customer, product, address):
    order = _place_cod_order(client, customer, product, address)
    html = client.get(f"/orders/{order.id}").get_data(as_text=True)
    assert to_ist(order.created_at).strftime("%d %b %Y, %I:%M %p IST") in html


def test_customer_cancel_defaults_to_first_reason(client, customer, product, address):
    order = _place_cod_order(client, customer, product, address, quantity=2)
    stock_before = reload(product).stock_quantity

    html = client.get(f"/orders/{order.id}").get_data(as_text=True)
    assert 'id="cancelOrderModal"' in html
    assert f'value="{OrderStatus.CANCEL_REASONS[0]}" checked' in html

    client.post(f"/checkout/cancel/{order.id}")
    order = reload(order)
    assert order.order_status == OrderStatus.CANCELLED
    assert _last_note(order) == f"Cancelled by customer: {OrderStatus.CANCEL_REASONS[0]}"
    assert reload(product).stock_quantity == stock_before + 2


def test_customer_cancel_records_chosen_reason_and_details(client, customer, product, address):
    order = _place_cod_order(client, customer, product, address)
    client.post(
        f"/checkout/cancel/{order.id}",
        data={"reason": "Changed my mind", "reason_details": "Bought it in store"},
    )
    assert _last_note(reload(order)) == "Cancelled by customer: Changed my mind (Bought it in store)"


def test_other_reason_needs_details(client, customer, product, address):
    order = _place_cod_order(client, customer, product, address)
    resp = client.post(f"/checkout/cancel/{order.id}", data={"reason": "Other"}, follow_redirects=True)
    assert b"tell us why" in resp.data
    assert reload(order).order_status == OrderStatus.PLACED

    client.post(f"/checkout/cancel/{order.id}", data={"reason": "Other", "reason_details": "Gift no longer needed"})
    assert _last_note(reload(order)) == "Cancelled by customer: Gift no longer needed"


def test_customer_cannot_cancel_once_packed(client, customer, product, address):
    order = _place_cod_order(client, customer, product, address)
    order.order_status = OrderStatus.PACKED
    order.put()

    assert 'id="cancelOrderModal"' not in client.get(f"/orders/{order.id}").get_data(as_text=True)
    client.post(f"/checkout/cancel/{order.id}")
    assert reload(order).order_status == OrderStatus.PACKED


def test_customer_cannot_cancel_someone_elses_order(client, customer, other_customer, product, address):
    order = _place_cod_order(client, customer, product, address)
    client.get("/logout")
    login(client, other_customer.email)
    resp = client.post(f"/checkout/cancel/{order.id}")
    assert resp.status_code == 404
    assert reload(order).order_status == OrderStatus.PLACED


def test_admin_cancel_uses_preset_reason(client, admin_user, customer, product, address):
    order = _place_cod_order(client, customer, product, address)
    client.get("/logout")
    admin_login(client, admin_user.email)

    html = client.get(f"/admin/orders/{order.id}").get_data(as_text=True)
    assert 'name="cancel_reason"' in html

    client.post(
        f"/admin/orders/{order.id}/status",
        data={"new_status": "cancelled", "cancel_reason": "Item out of stock", "note": "Supplier delay"},
    )
    order = reload(order)
    assert order.order_status == OrderStatus.CANCELLED
    assert _last_note(order) == "Item out of stock: Supplier delay"
