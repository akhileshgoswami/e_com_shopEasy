from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from flask import abort
from google.cloud import ndb

_CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class UTCDateTimeProperty(ndb.DateTimeProperty):
    """Stored as UTC, always read back as a timezone-aware datetime —
    including the in-memory value auto_now/auto_now_add set on put(), which
    stock NDB leaves naive until the entity is re-read."""

    def __init__(self, *args, tzinfo=timezone.utc, **kwargs):
        super().__init__(*args, tzinfo=tzinfo, **kwargs)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)


class DecimalProperty(ndb.IntegerProperty):
    """Money stored as integer paise: exact (no float rounding) and still
    sortable/comparable in Datastore queries. Reads back as Decimal("0.00")."""

    def _validate(self, value):
        try:
            return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            raise ndb.exceptions.BadValueError(f"Expected a decimal amount, got {value!r}")

    def _to_base_type(self, value):
        return int(value * 100)

    def _from_base_type(self, value):
        return (Decimal(value) / 100).quantize(_CENT)


class BaseModel(ndb.Model):
    """Integer auto-allocated ids (so URLs and templates keep using
    ``obj.id``) plus the created/updated timestamps every kind carries."""

    created_at = UTCDateTimeProperty(auto_now_add=True)
    updated_at = UTCDateTimeProperty(auto_now=True)

    @property
    def id(self):
        return self.key.id() if self.key else None

    @classmethod
    def find(cls, entity_id):
        """get_by_id() that tolerates the None/str ids that arrive from
        forms, URLs, JSON bodies and the session."""
        try:
            entity_id = int(entity_id)
        except (TypeError, ValueError):
            return None
        if entity_id <= 0:
            return None
        return cls.get_by_id(entity_id)

    @classmethod
    def find_or_404(cls, entity_id):
        entity = cls.find(entity_id)
        if entity is None:
            abort(404)
        return entity

    @classmethod
    def find_many(cls, ids):
        """{id: entity} for the ids that exist."""
        ids = [int(i) for i in ids if i]
        if not ids:
            return {}
        entities = ndb.get_multi([ndb.Key(cls, i) for i in ids])
        return {e.id: e for e in entities if e is not None}

    @classmethod
    def first(cls, *filters):
        return cls.query(*filters).get()

    @classmethod
    def all(cls, *filters):
        return cls.query(*filters).fetch()
