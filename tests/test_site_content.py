from app.models import SiteContent
from app.services.site_content_service import SiteContentService
from tests.conftest import admin_login, login


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


def test_admin_can_update_about_page(client, admin_user, db):
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

    row = SiteContent.query.filter_by(key="about_body").first()
    assert row is not None
    assert "luxury story" in row.value

    public_resp = client.get("/about")
    assert b"luxury story" in public_resp.data
    assert b"Second paragraph here" in public_resp.data


def test_admin_can_update_contact_info(client, admin_user, db):
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


def test_nl2p_escapes_html_input(client, admin_user, db):
    admin_login(client, admin_user.email)
    client.post(
        "/admin/content/about_body/edit",
        data={"value": "<script>alert(1)</script>\n\nSafe paragraph."},
    )
    resp = client.get("/about")
    assert b"<script>alert(1)</script>" not in resp.data
    assert b"&lt;script&gt;" in resp.data


def test_site_content_service_falls_back_to_default_without_db_row(app, db):
    with app.app_context():
        assert SiteContentService.get("contact_phone") == "+91 98765 43210"
