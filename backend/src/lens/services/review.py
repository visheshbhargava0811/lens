"""Review queue for held story summaries (G-OUT-07, docs/09 admin). A person approves or rejects;
approval publishes that exact verified version. Used by the admin API and `make review`."""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.db.models import ReviewQueueItem, Story, StorySummary
from lens.db.session import get_engine


def open_items(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(ReviewQueueItem, StorySummary, Story)
        .join(StorySummary, StorySummary.id == ReviewQueueItem.ref_id)
        .join(Story, Story.id == StorySummary.story_id)
        .where(ReviewQueueItem.status == "open", ReviewQueueItem.kind == "story_summary")
        .order_by(ReviewQueueItem.created_at)
    ).all()
    return [
        {
            "id": str(item.id),
            "reason": item.reason,
            "created_at": item.created_at.isoformat(),
            "story": {"id": str(story.id), "slug": story.slug, "headline": story.headline},
            "summary_version": summary.version,
            "summary": [s["text"] for s in summary.summary],
            "agreements": [s["text"] for s in summary.agreements],
            "disagreements": [s["text"] for s in summary.disagreements],
        }
        for item, summary, story in rows
    ]


def resolve(session: Session, item_id: uuid.UUID, decision: Literal["approve", "reject"], reviewer: str) -> bool:
    """Returns False if there is no such open item."""
    item = session.get(ReviewQueueItem, item_id)
    if item is None or item.status != "open":
        return False
    summary = session.get_one(StorySummary, item.ref_id)
    summary.state = "published" if decision == "approve" else "rejected"
    item.status, item.assigned_to, item.resolved_at = decision + "d", reviewer, datetime.now(UTC)
    return True


def main() -> int:
    """make review            list open items
    make review ARGS="approve <id>"   or   ARGS="reject <id>" """
    args = sys.argv[1:]
    with Session(get_engine()) as session, session.begin():
        if not args:
            items = open_items(session)
            for it in items:
                print(f"\n{it['id']}  [{it['reason']}]  {it['story']['headline']}")
                for s in it["summary"] + it["agreements"] + it["disagreements"]:
                    print(f"   - {s}")
            print(f"\n{len(items)} open")
            return 0
        decision, item_id = args[0], uuid.UUID(args[1])
        if decision not in ("approve", "reject"):
            print("usage: approve <id> | reject <id>")
            return 2
        ok = resolve(session, item_id, decision, reviewer="cli")  # type: ignore[arg-type]
        print("done" if ok else "no open item with that id")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
