from decimal import Decimal

from app.checkout.services import CheckoutService
from app.services.site_content_service import StorefrontService
from tests.conftest import admin_login, login

VALID = {
    "accent_color": "#12AB34",
    "free_shipping_threshold": "5000",
    "shipping_charge": "79",
    "tax_rate_percent": "18",
    "topbar_enabled": "y",
    "topbar_perk_1": "Ships free over ₹{free_delivery}",
    "topbar_perk_2": "",
    "topbar_perk_3": "",
    "hero_secondary_text": "Hot deals",
    "hero_perk_1": "Quality checked",
    "hero_perk_2": "",
    "hero_perk_3": "",
    "hero_sticker": "",
    "hero_collage_enabled": "y",
    "finder_enabled": "y",
    "finder_title": "Search the catalogue",
    "finder_placeholder": "Type anything",
    "finder_button": "Go",
    "finder_deals_label": "Sale items",
    "coupon_enabled": "",
    "coupon_text": "Hidden strip",
    "coupon_link_text": "",
}


def test_defaults_come_from_config(app):
    settings = StorefrontService.get()
    assert settings["free_shipping_threshold"] == Decimal("999")
    assert settings["shipping_charge"] == Decimal("49")
    assert settings["finder_enabled"] is True
    assert settings["topbar_perk_1"] == "Free delivery over ₹999"


def test_admin_saves_storefront_and_homepage_reflects_it(client, admin_user, category):
    admin_login(client, admin_user.email)
    assert client.get("/admin/storefront").status_code == 200

    resp = client.post("/admin/storefront", data=VALID, follow_redirects=True)
    assert b"Storefront updated." in resp.data

    html = client.get("/").get_data(as_text=True)
    assert "--pop: #12ab34;" in html
    assert "Ships free over ₹5,000" in html
    assert "Search the catalogue" in html
    assert "Hot deals" in html
    assert "Sale items" in html
    assert "Hidden strip" not in html  # offer strip switched off
    assert "sky-sticker" not in html  # empty sticker hidden


def test_finder_can_be_hidden(client, admin_user):
    admin_login(client, admin_user.email)
    client.post("/admin/storefront", data={**VALID, "finder_enabled": ""})
    assert b"sky-finder" not in client.get("/").data


def test_shipping_and_tax_rules_apply_at_checkout(client, admin_user, customer, product):
    admin_login(client, admin_user.email)
    client.post("/admin/storefront", data=VALID)
    client.get("/logout")

    login(client, customer.email)
    client.post("/cart/add", data={"product_id": product.id, "quantity": 1})
    summary = CheckoutService.build_summary(customer)
    assert summary["shipping_charge"] == Decimal("79")  # 1000 < 5000 threshold
    assert summary["tax"] == Decimal("180.00")
    assert summary["total"] == Decimal("1259.00")


def test_invalid_values_rejected(client, admin_user):
    admin_login(client, admin_user.email)
    resp = client.post("/admin/storefront", data={**VALID, "accent_color": "red", "tax_rate_percent": "150"})
    assert b"Storefront updated." not in resp.data
    assert StorefrontService.get()["tax_rate_percent"] == Decimal("0")


def test_customer_cannot_edit_storefront(client, customer):
    login(client, customer.email)
    assert client.get("/admin/storefront").status_code == 403
