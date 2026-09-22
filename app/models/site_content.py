from datetime import datetime, timezone

from app.extensions import db


class SiteContent(db.Model):
    """Admin-editable site copy (About, Privacy Policy, Terms, contact info)
    so these pages can be updated without a code deploy."""

    __tablename__ = "site_content"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), nullable=False, unique=True, index=True)
    label = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<SiteContent {self.key}>"
