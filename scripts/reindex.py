"""Rebuild the chunk store and every vector index from the stored materials.

Run this once after upgrading to id-keyed retrieval, and any time an index and
its chunk store have drifted apart beyond what `ensure_meeting_indexed` fixes
on its own.

    .venv/Scripts/python.exe -m scripts.reindex           # report only
    .venv/Scripts/python.exe -m scripts.reindex --apply   # rebuild

Nothing is written without `--apply`. Material text is the source of truth
throughout: chunks and vectors are both derived from it, so a rebuild is always
safe to repeat.
"""

from __future__ import annotations

import argparse
import sys

from core.config import get_settings
from core.db import Database
from core.embed import get_embedder
from core.indexing import check_index, rebuild_meeting_index
from core.logging_config import configure_logging
from core.migrations import backup_database

# Indices written before retrieval was keyed on chunk ids. They store insertion
# positions, which cannot be mapped back to any particular chunk, so they are
# rebuilt rather than migrated.
LEGACY_SUFFIX = ".index"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually rebuild; without it the script only reports",
    )
    parser.add_argument(
        "--keep-legacy",
        action="store_true",
        help="leave the pre-overhaul .index files in place",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    db = Database(settings.db_path)

    meetings = db.list_meetings()
    print(f"Database: {settings.db_path}")
    print(f"Indices:  {settings.faiss_dir}")
    print(f"Meetings: {len(meetings)}\n")

    for meeting in meetings:
        materials = db.get_materials(meeting.id)
        health = check_index(db, meeting.id, settings=settings)
        print(
            f"  {meeting.id}  {meeting.title[:40]:<40} "
            f"{len(materials)} materials, {health.stored} chunks, "
            f"{health.indexed} vectors"
        )

    if not args.apply:
        print("\nDry run. Re-run with --apply to rebuild.")
        return 0

    backup = backup_database(settings.db_path)
    print(f"\nBacked up database to {backup}")

    # Touch the embedder before the loop so a missing model fails immediately
    # rather than after the first meeting has already been rewritten.
    get_embedder(settings)

    total_chunks = 0
    for meeting in meetings:
        report = rebuild_meeting_index(db, meeting.id, settings=settings)
        total_chunks += report.chunks
        print(f"  rebuilt {report}")

    print(f"\nTotal: {total_chunks} chunks across {len(meetings)} meetings")

    unhealthy = [m.id for m in meetings if not check_index(db, m.id, settings=settings).healthy]
    if unhealthy:
        print(f"STILL OUT OF SYNC: {unhealthy}", file=sys.stderr)
        return 1

    if not args.keep_legacy:
        stale = sorted(settings.faiss_dir.glob(f"*{LEGACY_SUFFIX}"))
        for path in stale:
            path.unlink()
        if stale:
            print(f"Removed {len(stale)} pre-overhaul index files")

    print("All meetings consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
