from app.models import CartItem, Order, Product, SiteContent
from app.payments.razorpay_service import RazorpayService
from app.services.payment_settings_service import PaymentSettingsService
from tests.conftest import admin_login, login, reload

SETTINGS_URL = "/admin/payments/settings"


def _save(client, **overrides):
    data = {
        "cod_enabled": "y",
        "razorpay_enabled": "y",
        "razorpay_key_id": "",
        "razorpay_key_secret": "",
        "razorpay_webhook_secret": "",
        **overrides,
    }
    return client.post(SETTINGS_URL, data={k: v for k, v in data.items() if v is not None}, follow_redirects=True)


def _second_product(category):
    p = Product(category_id=category.id, name="Spare Charger", slug="spare-charger", sku="SKU-CHG-1", price=500, stock_quantity=5)
    p.put()
    return p


# ---------- Payment settings ----------

def test_env_keys_are_the_default(app):
    settings = PaymentSettingsService.get()
    assert settings["razorpay_key_id"] == "rzp_test_key_id"
    assert settings["razorpay_key_id_source"] == "env"
    assert PaymentSettingsService.enabled_methods() == ["cod", "razorpay"]


def test_admin_keys_override_env_and_secrets_are_encrypted(client, admin_user):
    admin_login(client, admin_user.email)
    resp = _save(
        client,
        razorpay_key_id="rzp_live_ABCDEF123456",
        razorpay_key_secret="super-secret-value-9876",
        razorpay_webhook_secret="hook-secret-5555",
    )
    assert b"Payment settings saved." in resp.data

    settings = PaymentSettingsService.get()
    assert settings["razorpay_key_id"] == "rzp_live_ABCDEF123456"
    assert settings["razorpay_key_secret"] == "super-secret-value-9876"
    assert settings["razorpay_webhook_secret"] == "hook-secret-5555"
    assert settings["razorpay_mode"] == "live"
    assert RazorpayService.public_key_id() == "rzp_live_ABCDEF123456"

    stored = SiteContent.get_by_id("payment_razorpay_key_secret").value
    assert "super-secret-value-9876" not in stored

    page = client.get(SETTINGS_URL).get_data(as_text=True)
    assert "super-secret-value-9876" not in page and "hook-secret-5555" not in page
    assert "••••9876" in page


def test_blank_secret_keeps_saved_value_and_clear_restores_env(client, admin_user):
    admin_login(client, admin_user.email)
    _save(client, razorpay_key_id="rzp_test_NEWKEY", razorpay_key_secret="first-secret")
    _save(client, razorpay_key_id="rzp_test_NEWKEY")  # secret left blank
    assert PaymentSettingsService.get()["razorpay_key_secret"] == "first-secret"

    _save(client, clear_saved_keys="y")
    settings = PaymentSettingsService.get()
    assert settings["razorpay_key_id"] == "rzp_test_key_id"
    assert settings["razorpay_key_secret_source"] == "env"


def test_disabling_razorpay_hides_it_and_blocks_orders(client, admin_user, customer, product, address):
    admin_login(client, admin_user.email)
    _save(client, razorpay_enabled=None)
    client.get("/logout")

    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    page = client.get("/checkout").get_data(as_text=True)
    assert 'value="razorpay"' not in page and 'value="cod"' in page

    resp = client.post("/checkout/place", data={"address_id": address.id, "payment_method": "razorpay"}, follow_redirects=True)
    assert b"available payment method" in resp.data
    assert Order.first(Order.user_id == customer.id) is None


def test_invalid_settings_rejected(client, admin_user):
    admin_login(client, admin_user.email)
    assert b"at least one payment method" in _save(client, cod_enabled=None, razorpay_enabled=None).data
    assert b"rzp_test_ or rzp_live_" in _save(client, razorpay_key_id="sk_live_nope").data
    assert PaymentSettingsService.get()["razorpay_key_id_source"] == "env"


def test_customer_cannot_open_payment_settings(client, customer):
    login(client, customer.email)
    assert client.get(SETTINGS_URL).status_code == 403


# ---------- Buy now ----------

def test_buy_now_orders_only_that_item_and_keeps_cart(client, customer, product, category, address):
    charger = _second_product(category)
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 2})

    resp = client.post("/buy-now", data={"product_id": charger.id, "quantity": 1})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/checkout")

    page = client.get("/checkout").get_data(as_text=True)
    assert "Spare Charger" in page and "Test Phone" not in page
    assert "Buying just this item" in page

    client.post("/checkout/place", data={"address_id": address.id, "payment_method": "cod"})
    order = Order.first(Order.user_id == customer.id)
    assert [i.product_name for i in order.items] == ["Spare Charger"]
    assert reload(charger).stock_quantity == 4
    assert reload(product).stock_quantity == 10  # cart item untouched

    cart_lines = CartItem.all(CartItem.cart_id == customer.id)
    assert [(i.product_id, i.quantity) for i in cart_lines] == [(product.id, 2)]


def test_buy_now_requires_login_then_resumes_at_checkout(client, customer, product):
    resp = client.post("/buy-now", data={"product_id": product.id, "quantity": 1})
    assert "/login" in resp.headers["Location"]

    resp = client.post("/login", data={"email": customer.email, "password": "Passw0rd!"})
    assert resp.headers["Location"].endswith("/checkout")
    assert "Buying just this item" in client.get("/checkout").get_data(as_text=True)


def test_going_back_to_cart_cancels_buy_now(client, customer, product, category):
    charger = _second_product(category)
    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    client.post("/buy-now", data={"product_id": charger.id, "quantity": 1})

    client.get("/cart")
    page = client.get("/checkout").get_data(as_text=True)
    assert "Test Phone" in page and "Buying just this item" not in page


def test_buy_now_out_of_stock_rejected(client, customer, product):
    product.stock_quantity = 0
    product.put()
    login(client, customer.email)
    resp = client.post("/buy-now", data={"product_id": product.id, "quantity": 1}, follow_redirects=True)
    assert b"out of stock" in resp.data
