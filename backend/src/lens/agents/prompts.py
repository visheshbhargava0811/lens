"""Versioned prompt skills (docs/06 "Prompts and skills"): Markdown with front matter in agents/skills/."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

SKILLS = Path(__file__).parent / "skills"


@dataclass(frozen=True)
class Skill:
    name: str
    version: str
    text: str


@lru_cache
def skill(name: str) -> Skill:
    raw = (SKILLS / f"{name}.md").read_text(encoding="utf-8")
    _, front, body = raw.split("---", 2)
    meta = yaml.safe_load(front)
    return Skill(name=name, version=str(meta["version"]), text=body.strip())


def system_prompt(task: str) -> tuple[str, str]:
    """Shared evidence rules + the task skill. Returns (text, prompt_version) for tracing and storage."""
    rules, t = skill("evidence_rules"), skill(task)
    return f"{rules.text}\n\n{t.text}", f"{task}@{t.version}+evidence_rules@{rules.version}"
