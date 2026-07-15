from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp, matching the timezone-less DateTime columns."""

    return datetime.now(timezone.utc).replace(tzinfo=None)
