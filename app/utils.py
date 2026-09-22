from datetime import timezone


def as_aware_utc(dt):
    """Some DB backends (notably SQLite) drop tzinfo on round-trip even for
    timezone-aware columns. Normalize to an aware UTC datetime before any
    comparison so this never raises on naive-vs-aware comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
