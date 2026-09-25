from datetime import datetime, timedelta, timezone

from google.cloud import ndb

from app.models.base import BaseModel, UTCDateTimeProperty
from app.utils import as_aware_utc


class EmailStatus:
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CHOICES = (SENDING, SENT, FAILED)


class EmailOutbox(BaseModel):
    """One notification that must go out at most once, e.g. the confirmation
    for order 42. The entity id is the idempotency key
    ("order_confirmation:42"), so a retried request, the Razorpay webhook
    racing the browser callback, or a double-clicked admin form all resolve
    to the same row. The payload holds only ids, never rendered content or
    secrets; the email is rebuilt from the database when (re)sent."""

    kind = ndb.StringProperty(required=True)
    status = ndb.StringProperty(default=EmailStatus.SENDING)
    payload = ndb.JsonProperty()
    attempts = ndb.IntegerProperty(default=0, indexed=False)
    last_error = ndb.TextProperty()
    claimed_at = UTCDateTimeProperty(indexed=False)
    sent_at = UTCDateTimeProperty(indexed=False)

    MAX_ATTEMPTS = 5
    # A "sending" row this old belongs to a worker that died mid-send.
    STALE_AFTER = timedelta(minutes=10)

    @property
    def key_name(self):
        return self.key.id() if self.key else None

    @classmethod
    def claim(cls, key_name, kind, payload):
        """Atomically take the right to send this email. Returns the row, or
        None when it was already sent, is being sent right now, or has
        exhausted its retries."""

        def txn():
            now = datetime.now(timezone.utc)
            row = cls.get_by_id(key_name)
            if row is None:
                row = cls(id=key_name, kind=kind, payload=payload)
            elif row.status == EmailStatus.SENT:
                return None
            elif row.status == EmailStatus.SENDING and not row.is_stale(now):
                return None
            elif (row.attempts or 0) >= cls.MAX_ATTEMPTS:
                return None
            row.status = EmailStatus.SENDING
            row.attempts = (row.attempts or 0) + 1
            row.claimed_at = now
            row.put()
            return row

        return ndb.transaction(txn)

    def is_stale(self, now=None):
        now = now or datetime.now(timezone.utc)
        claimed = as_aware_utc(self.claimed_at)
        return claimed is None or claimed < now - self.STALE_AFTER

    def mark_sent(self):
        self.status = EmailStatus.SENT
        self.sent_at = datetime.now(timezone.utc)
        self.last_error = None
        self.put()

    def mark_failed(self, error):
        self.status = EmailStatus.FAILED
        self.last_error = (error or "")[:500]
        self.put()

    @classmethod
    def retryable(cls):
        """Failed rows with attempts left, plus rows stuck in "sending"."""
        failed = cls.all(cls.status == EmailStatus.FAILED)
        stuck = [r for r in cls.all(cls.status == EmailStatus.SENDING) if r.is_stale()]
        return [r for r in failed + stuck if (r.attempts or 0) < cls.MAX_ATTEMPTS]

    def __repr__(self):
        return f"<EmailOutbox {self.key_name} {self.status}>"
