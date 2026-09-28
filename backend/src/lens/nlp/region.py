"""Story region (state) for the Local tab (F-15), from the URL sections outlets file local news under.

Deterministic, no model: each article URL's path is read right to left (the most specific section wins,
so delhi-ncr/noida is Uttar Pradesh), and a story gets a state only when `min_share` of all its articles
point to it. National stories with one local copy stay unregioned. Config: config/regions.yaml.

    python -m lens.nlp.region      # backfill every story
"""

from __future__ import annotations

import sys
import uuid
from collections import Counter, defaultdict
from functools import lru_cache
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.db.models import Article, Story, StoryArticle


@lru_cache
def _lookup() -> tuple[dict[str, str], float]:
    cfg = load_yaml("regions.yaml")
    table = {s: s for s in load_yaml("memory.yaml")["values"]["followed_regions"]}
    for state, names in cfg["aliases"].items():
        assert state in table, f"regions.yaml: unknown state {state}"
        table.update({n: state for n in names})
    return table, float(cfg["min_share"])


def url_region(url: str) -> str | None:
    table, _ = _lookup()
    sections = [p.lower().removesuffix("-news") for p in urlsplit(url).path.split("/") if p][:-1]  # last = article
    return next((table[s] for s in reversed(sections) if s in table), None)


def story_region(urls: list[str]) -> str | None:
    _, min_share = _lookup()
    votes = Counter(r for r in map(url_region, urls) if r)
    if not votes:
        return None
    (state, n), *rest = votes.most_common(2)
    tied = bool(rest) and rest[0][1] == n  # split between two states: neither is the story's
    return state if not tied and n / len(urls) >= min_share else None


def tag_all(session: Session) -> int:
    """Sets stories.region for every story; returns how many changed."""
    urls: dict[uuid.UUID, list[str]] = defaultdict(list)
    for sid, url in session.execute(
        select(StoryArticle.story_id, Article.url).join(Article, Article.id == StoryArticle.article_id)
    ):
        urls[sid].append(url)
    current = dict(session.execute(select(Story.id, Story.region)).all())
    new = {sid: story_region(u) for sid, u in urls.items()}
    changed = [(sid, r) for sid, r in new.items() if r != current.get(sid)]
    for sid, region in changed:
        session.execute(update(Story).where(Story.id == sid).values(region=region))
    return len(changed)


if __name__ == "__main__":
    from lens.db.session import get_engine

    with Session(get_engine()) as s, s.begin():
        print({"stories_changed": tag_all(s)})
    sys.exit(0)
