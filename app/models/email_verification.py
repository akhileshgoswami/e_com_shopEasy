from google.cloud import ndb

from app.models.base import BaseModel, UTCDateTimeProperty


class EmailVerificationCode(BaseModel):
    """The one live sign-up code for an account. The entity id is the user
    id, so issuing a new code replaces the old one. Only a keyed hash
    (HMAC with SECRET_KEY) of the 6-digit code is stored: a plain hash of a
    6-digit number could be reversed by trying all million values."""

    code_hash = ndb.TextProperty(required=True)
    expires_at = UTCDateTimeProperty(required=True, indexed=False)
    failed_attempts = ndb.IntegerProperty(default=0, indexed=False)
    last_sent_at = UTCDateTimeProperty(indexed=False)
    # Send timestamps within the last hour, for the per-account resend cap.
    recent_sends = UTCDateTimeProperty(repeated=True, indexed=False)

    @classmethod
    def key_for(cls, user_id):
        return ndb.Key(cls, int(user_id))

    def __repr__(self):
        return f"<EmailVerificationCode user={self.key.id() if self.key else None}>"
