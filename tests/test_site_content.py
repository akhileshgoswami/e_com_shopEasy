from app.models import SiteContent
from app.services.site_content_service import SiteContentService
from tests.conftest import admin_login, fake_image_bytes, login


def test_public_pages_render_default_content_before_any_edit(client):
    resp = client.get("/about")
    assert b"ShopEasy is an online store" in resp.data

    resp = client.get("/privacy-policy")
    assert b"PCI-DSS compliant" in resp.data

    resp = client.get("/contact")
    assert b"support@example.com" in resp.data


def test_customer_cannot_edit_site_content(client, customer):
    login(client, customer.email)
    resp = client.get("/admin/content")
    assert resp.status_code == 403


def test_admin_can_update_about_page(client, admin_user):
    admin_login(client, admin_user.email)

    resp = client.get("/admin/content")
    assert resp.status_code == 200
    assert b"About us" in resp.data

    resp = client.post(
        "/admin/content/about_body/edit",
        data={"value": "This is our brand new luxury story.\n\nSecond paragraph here."},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    row = SiteContent.get_by_id("about_body")
    assert row is not None
    assert "luxury story" in row.value

    public_resp = client.get("/about")
    assert b"luxury story" in public_resp.data
    assert b"Second paragraph here" in public_resp.data


def test_admin_can_update_contact_info(client, admin_user):
    admin_login(client, admin_user.email)
    resp = client.post(
        "/admin/content/contact_email/edit",
        data={"value": "hello@luxuryshop.example"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    public_resp = client.get("/contact")
    assert b"hello@luxuryshop.example" in public_resp.data


def test_unknown_content_key_404s(client, admin_user):
    admin_login(client, admin_user.email)
    resp = client.get("/admin/content/not-a-real-key/edit")
    assert resp.status_code == 404


def test_nl2p_escapes_html_input(client, admin_user):
    admin_login(client, admin_user.email)
    client.post(
        "/admin/content/about_body/edit",
        data={"value": "<script>alert(1)</script>\n\nSafe paragraph."},
    )
    resp = client.get("/about")
    assert b"<script>alert(1)</script>" not in resp.data
    assert b"&lt;script&gt;" in resp.data


def test_site_content_service_falls_back_to_default_without_db_row(app):
    with app.app_context():
        assert SiteContentService.get("contact_phone") == "+91 98765 43210"


def test_admin_can_update_branding(client, admin_user):
    admin_login(client, admin_user.email)

    resp = client.get("/admin/settings")
    assert resp.status_code == 200
    assert b"Website name" in resp.data

    resp = client.post(
        "/admin/settings",
        data={"site_name": "Luxe Mart", "theme_color": "#1F6FB2"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    resp = client.get("/")
    assert b"Luxe Mart" in resp.data
    assert b"--gold: #1f6fb2;" in resp.data
    assert b"--gold-rgb: 31, 111, 178;" in resp.data


def test_branding_rejects_invalid_color(client, admin_user):
    admin_login(client, admin_user.email)
    resp = client.post("/admin/settings", data={"site_name": "Luxe Mart", "theme_color": "red; }"})
    assert b"Use a hex color" in resp.data
    assert SiteContent.get_by_id("theme_color") is None


def test_customer_cannot_update_branding(client, customer):
    login(client, customer.email)
    resp = client.post("/admin/settings", data={"site_name": "Hacked", "theme_color": "#000000"})
    assert resp.status_code == 403


def test_home_banner_shows_default_copy(client):
    resp = client.get("/")
    assert b"Everyday essentials, elevated." in resp.data
    assert b"has-image" not in resp.data


def test_admin_can_upload_and_remove_banner_image(client, admin_user):
    admin_login(client, admin_user.email)

    resp = client.post(
        "/admin/settings/banner",
        data={
            "banner-eyebrow": "Festive sale",
            "banner-title": "Diwali deals are live",
            "banner-subtitle": "Up to 50% off.",
            "banner-button_text": "Shop deals",
            "banner-image": (fake_image_bytes(), "banner.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Homepage banner updated." in resp.data

    image_url = SiteContent.get_by_id("hero_image_url").value
    assert "banners" in image_url

    resp = client.get("/")
    assert b"Diwali deals are live" in resp.data
    assert b"Shop deals" in resp.data
    assert b"has-image" in resp.data
    assert image_url.encode() in resp.data

    client.post(
        "/admin/settings/banner",
        data={
            "banner-eyebrow": "",
            "banner-title": "",
            "banner-subtitle": "",
            "banner-button_text": "",
            "banner-remove_image": "y",
        },
        content_type="multipart/form-data",
    )
    resp = client.get("/")
    assert b"has-image" not in resp.data
    assert b"Everyday essentials, elevated." in resp.data


def test_customer_cannot_update_banner(client, customer):
    login(client, customer.email)
    resp = client.post("/admin/settings/banner", data={"banner-title": "Hacked"})
    assert resp.status_code == 403


def test_admin_can_upload_and_remove_logo(client, admin_user):
    admin_login(client, admin_user.email)

    resp = client.post(
        "/admin/settings",
        data={
            "site_name": "Luxe Mart",
            "theme_color": "#b8873f",
            "logo": (fake_image_bytes(), "logo.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Branding updated." in resp.data

    logo_url = SiteContent.get_by_id("logo_url").value
    assert "branding" in logo_url

    resp = client.get("/")
    assert logo_url.encode() in resp.data
    assert b'class="brand-logo"' in resp.data
    assert b'<span class="brand-name">Luxe Mart</span>' not in resp.data  # unchecked box -> hide name

    client.post(
        "/admin/settings",
        data={"site_name": "Luxe Mart", "theme_color": "#b8873f", "remove_logo": "y", "show_name_with_logo": "y"},
        content_type="multipart/form-data",
    )
    resp = client.get("/")
    assert b'class="brand-logo"' not in resp.data
    assert b'<span class="brand-name">Luxe Mart</span>' in resp.data


def test_admin_can_change_fonts(client, admin_user):
    admin_login(client, admin_user.email)

    resp = client.get("/")
    assert b"@fontsource/poppins@5/700.css" in resp.data
    assert b"@fontsource/inter@5/400.css" in resp.data

    resp = client.post(
        "/admin/settings",
        data={"site_name": "ShopEasy", "theme_color": "#b8873f", "heading_font": "playfair-display", "body_font": "lato"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Branding updated." in resp.data

    resp = client.get("/")
    assert b"@fontsource/playfair-display@5/700.css" in resp.data
    assert b"@fontsource/lato@5/400.css" in resp.data
    assert b"@fontsource/lato@5/500.css" not in resp.data  # Lato ships no 500 weight
    assert b'--font-display: "Playfair Display"' in resp.data
    assert b'--font-body: "Lato"' in resp.data


def test_branding_rejects_unknown_font(client, admin_user):
    admin_login(client, admin_user.email)
    client.post(
        "/admin/settings",
        data={"site_name": "ShopEasy", "theme_color": "#b8873f", "heading_font": "evil;}", "body_font": "inter"},
        content_type="multipart/form-data",
    )
    assert SiteContent.get_by_id("heading_font") is None
