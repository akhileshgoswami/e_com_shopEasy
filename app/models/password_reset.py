import hashlib

from google.cloud import ndb

from app.models.base import BaseModel, UTCDateTimeProperty


class PasswordResetToken(BaseModel):
    """One emailed password-reset link. The entity id is the SHA-256 of the
    token, so the link itself is never stored and "which request is this?"
    is a strongly consistent key lookup. The token carries 256 bits of
    randomness, so a fast hash is enough — there is nothing to brute-force."""

    user_id = ndb.IntegerProperty(required=True)
    expires_at = UTCDateTimeProperty(required=True, indexed=False)
    used_at = UTCDateTimeProperty(indexed=False)
    # Set when a newer link for the same account made this one obsolete.
    superseded = ndb.BooleanProperty(default=False, indexed=False)

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def key_for(cls, token):
        return ndb.Key(cls, cls.hash_token(token))

    @classmethod
    def for_user(cls, user_id):
        return cls.all(cls.user_id == user_id)

    def __repr__(self):
        return f"<PasswordResetToken user={self.user_id} used={bool(self.used_at)}>"
