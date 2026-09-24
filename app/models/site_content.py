from google.cloud import ndb

from app.models.base import BaseModel


class SiteContent(BaseModel):
    """Admin-editable site copy (About, Privacy Policy, Terms, contact info)
    so these pages can be updated without a code deploy. The entity id is
    the content key (e.g. "about_body"), so each key exists at most once."""

    label = ndb.TextProperty(required=True)
    value = ndb.TextProperty(default="")

    @property
    def content_key(self):
        return self.key.id() if self.key else None

    @classmethod
    def get_many(cls, content_keys):
        """{content_key: row} for the keys that have been saved."""
        rows = ndb.get_multi([ndb.Key(cls, k) for k in content_keys])
        return {row.content_key: row for row in rows if row is not None}

    def __repr__(self):
        return f"<SiteContent {self.content_key}>"
