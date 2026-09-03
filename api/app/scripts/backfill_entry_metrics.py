"""Populate consumption metrics on entries created before they were tracked.

Runs automatically in the background on API startup unless
BACKFILL_METRICS_ON_STARTUP=false - see run_on_startup below. Can also be run
by hand, which is the way to get a dry run, a bounded pass, or an immediate
result without a restart. It performs one S3 HEAD per entry with an unknown
size:

    docker compose exec api python -m app.scripts.backfill_entry_metrics
    docker compose exec api python -m app.scripts.backfill_entry_metrics --dry-run

Entries are examined in primary-key order, in batches of BATCH_SIZE with a
commit after each batch, so the whole table is never materialised at once and
no single transaction stays open across an O(entries) sequence of S3
round-trips. An interrupted run keeps every batch it already committed.

`--limit N` bounds how many entries this run EXAMINES, not how many it ends up
updating; `--limit 0` examines nothing. Some entries can never be completed —
no object in S3, or a pasted transcript that has no audio and therefore no
duration — so they keep matching the "some metric is NULL" filter forever.
`--offset N` skips the first N matching entries so an operator can page through
the table across runs instead of re-examining the same oldest rows:

    ... --limit 500                 # first 500 examined
    ... --offset 500 --limit 500    # next 500 examined

The offset is relative to the current matching set, which shrinks as entries
are filled in.

Idempotent: only NULL fields are written, so re-running costs nothing. Writes
go through a Core UPDATE that restores the row's existing `updated_at`, so a
maintenance run never re-dates a user's library.
"""

import argparse
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import or_, update
from sqlalchemy.orm import Session, lazyload

from app.db.database import SessionLocal, engine
from app.models.entry import Entry
from app.services.entry_metrics import (
    count_words,
    duration_from_segments,
    parse_json_list,
)
from app.services.s3_service import S3Service

# Entries loaded (and committed) per round trip. Small enough that a batch's S3
# HEADs cannot hold a transaction open for long, large enough to keep the
# number of round trips sane.
BATCH_SIZE = 200


def compute_missing_metrics(entry, s3_service) -> dict[str, Any]:
    """Return only the metric fields that are NULL and can be derived now."""

    updates: dict[str, Any] = {}

    if entry.file_size_bytes is None and entry.file_path:
        info = s3_service.get_file_info(entry.file_path)
        if info and info.get("size") is not None:
            updates["file_size_bytes"] = int(info["size"])

    if entry.duration_seconds is None:
        duration = duration_from_segments(parse_json_list(entry.transcript_segments))
        if duration is not None:
            updates["duration_seconds"] = duration

    if entry.word_count is None:
        words = count_words(entry.transcript, parse_json_list(entry.transcript_words))
        if words is not None:
            updates["word_count"] = words

    return updates


def _fetch_batch(
    db: Session,
    *,
    after_id: UUID | None,
    offset: int,
    size: int,
) -> list[Entry]:
    """One page of entries missing at least one metric, in primary-key order.

    Paging uses an id cursor rather than a growing OFFSET: filling in metrics
    removes rows from the filter mid-run, which would make an offset window
    skip entries.
    """

    query = db.query(Entry).filter(
        or_(
            Entry.file_size_bytes.is_(None),
            Entry.duration_seconds.is_(None),
            Entry.word_count.is_(None),
        ),
    )
    if after_id is not None:
        query = query.filter(Entry.id > after_id)
    # Entry.owner is lazy="joined"; the backfill never reads it, so drop the
    # user join instead of dragging a row of it along per entry.
    query = query.options(lazyload(Entry.owner)).order_by(Entry.id)
    if offset:
        query = query.offset(offset)
    return query.limit(size).all()


def backfill(
    db: Session,
    s3_service,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    offset: int = 0,
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Fill in NULL metrics, committing per batch.

    `limit` caps the number of entries examined; None means "all of them" and
    0 (or less) means "none of them". `offset` skips that many matching
    entries before the first batch.
    """

    counters = {"scanned": 0, "updated": 0, "failed": 0}
    if limit is not None and limit <= 0:
        return counters

    remaining = limit
    after_id: UUID | None = None
    pending_offset = offset

    while True:
        size = batch_size if remaining is None else min(batch_size, remaining)
        entries = _fetch_batch(
            db,
            after_id=after_id,
            offset=pending_offset,
            size=size,
        )
        if not entries:
            break

        for entry in entries:
            counters["scanned"] += 1
            try:
                updates = compute_missing_metrics(entry, s3_service)
            except Exception as exc:  # one unreachable object must not stop the run
                counters["failed"] += 1
                logger.warning(f"Entry {entry.id}: backfill failed — {exc}")
                continue

            if not updates:
                continue

            counters["updated"] += 1
            if dry_run:
                continue

            # Core UPDATE rather than ORM attribute writes: naming updated_at in
            # values() suppresses its onupdate=datetime.utcnow, so the row keeps
            # the timestamp the user last saw.
            db.execute(
                update(Entry)
                .where(Entry.id == entry.id)
                .values(updated_at=entry.updated_at, **updates),
            )

        # Read before the commit below expires these instances.
        after_id = entries[-1].id
        pending_offset = 0

        if dry_run:
            db.rollback()
        else:
            db.commit()

        if remaining is not None:
            remaining -= len(entries)
            if remaining <= 0:
                break
        if len(entries) < size:
            break

    return counters


# Identifies this job among all pg_try_advisory_lock users on the database.
# Arbitrary but must never change, or two versions of the API would each think
# they hold "the" backfill lock.
STARTUP_LOCK_KEY = 8_641_207_314_552_001


def run_on_startup() -> dict[str, int] | None:
    """Backfill in the background while the API serves requests.

    Blocking and S3-bound (one HEAD per entry with an unknown size), so callers
    MUST run this off the event loop - see the lifespan handler in app.main.

    Returns the counters, or None when another process holds the lock. Never
    raises: a failed maintenance pass must not take the API down with it.
    """

    lock_conn = engine.connect()
    try:
        # A session-level advisory lock on its own connection, not the
        # backfill's: the backfill commits per batch, which returns its
        # connection to the pool, and a lock follows the connection that took
        # it. try_ rather than a blocking acquire so replica number two skips
        # the pass instead of queueing to repeat it.
        acquired = lock_conn.exec_driver_sql(
            "SELECT pg_try_advisory_lock(%s)",
            (STARTUP_LOCK_KEY,),
        ).scalar()
        if not acquired:
            logger.info("Startup metrics backfill: already running elsewhere, skipped")
            return None

        db = SessionLocal()
        try:
            counters = backfill(db, S3Service())
        finally:
            db.close()

        if counters["scanned"]:
            logger.info(
                f"Startup metrics backfill: {counters['scanned']} scanned, "
                f"{counters['updated']} updated, {counters['failed']} failed",
            )
        return counters
    except Exception as exc:
        logger.warning(f"Startup metrics backfill failed: {exc}")
        return None
    finally:
        try:
            lock_conn.exec_driver_sql(
                "SELECT pg_advisory_unlock(%s)",
                (STARTUP_LOCK_KEY,),
            )
        except Exception:  # the connection is being discarded anyway
            pass
        lock_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "examine at most N entries this run (not 'update N'); 0 examines "
            "nothing. Default: examine every entry with a missing metric."
        ),
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help=(
            "skip the first N matching entries before examining, so runs can "
            "page past entries whose metrics are not derivable (default: 0)"
        ),
    )
    args = parser.parse_args()

    if args.limit is not None and args.limit < 0:
        parser.error("--limit must not be negative")
    if args.offset < 0:
        parser.error("--offset must not be negative")

    db = SessionLocal()
    try:
        counters = backfill(
            db,
            S3Service(),
            dry_run=args.dry_run,
            limit=args.limit,
            offset=args.offset,
        )
    finally:
        db.close()

    prefix = "[dry run] " if args.dry_run else ""
    logger.info(
        f"{prefix}Backfill finished: {counters['scanned']} scanned, "
        f"{counters['updated']} updated, {counters['failed']} failed",
    )


if __name__ == "__main__":
    main()
