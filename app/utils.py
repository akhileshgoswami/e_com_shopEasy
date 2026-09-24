import math
from datetime import timezone


def as_aware_utc(dt):
    """Normalize to an aware UTC datetime before any comparison so this
    never raises on naive-vs-aware comparisons (e.g. values set in code
    before an entity has round-tripped through Datastore)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def contains_text(needle, *haystacks):
    """Case-insensitive substring match — Datastore has no LIKE/ILIKE, so
    search filters run in Python over the already-fetched rows."""
    needle = (needle or "").strip().lower()
    return any(needle in (h or "").lower() for h in haystacks)


class Pagination:
    """Paginates an in-memory list, exposing the same attributes the
    templates used from Flask-SQLAlchemy's Pagination."""

    def __init__(self, items, page, per_page):
        items = list(items)
        self.page = max(int(page or 1), 1)
        self.per_page = per_page
        self.total = len(items)
        start = (self.page - 1) * per_page
        self.items = items[start : start + per_page]

    @property
    def pages(self):
        return math.ceil(self.total / self.per_page) if self.total else 0

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def iter_pages(self, *, left_edge=2, left_current=2, right_current=4, right_edge=2):
        """Page numbers to show, with None marking each elided gap."""
        pages_end = self.pages + 1
        if pages_end == 1:
            return
        left_end = min(1 + left_edge, pages_end)
        yield from range(1, left_end)
        if left_end == pages_end:
            return
        mid_start = max(left_end, self.page - left_current)
        mid_end = min(self.page + right_current + 1, pages_end)
        if mid_start - left_end > 0:
            yield None
        yield from range(mid_start, mid_end)
        if mid_end == pages_end:
            return
        right_start = max(mid_end, pages_end - right_edge)
        if right_start - mid_end > 0:
            yield None
        yield from range(right_start, pages_end)


def newest_first(entities):
    return sorted(entities, key=lambda e: e.created_at, reverse=True)
