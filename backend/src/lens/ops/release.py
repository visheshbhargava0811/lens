"""Release and one-command rollback (docs/08 "Release process", ADR-0039).

A release pins everything that changes model behaviour without a code change: the prompt skills, the
config files (model tier map, retrieval, guardrails, clustering, gates), the topic prototypes, and the
eval reports that vouch for them. `release` records their hashes, the prompt versions and the gate
results in releases/<name>.json, commits it and tags `release/<name>`. `rollback` restores those
files from the tag, checks them against the manifest, re-runs the gate and commits. Code is released
and reverted with git as usual.

    python -m lens.ops.release create <name>
    python -m lens.ops.release rollback <name>
    python -m lens.ops.release list
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from lens.core.settings import REPO_ROOT

PINNED = ["backend/src/lens/agents/skills", "config", "data/topics/prototypes.npz", "reports/eval"]


class ReleaseError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if r.returncode:
        raise ReleaseError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def pinned_files(root: Path) -> list[str]:
    out = []
    for p in PINNED:
        path = root / p
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        out += [str(f.relative_to(root)) for f in files if f.is_file() and not f.name.startswith(".")]
    return out


def file_hashes(root: Path) -> dict[str, str]:
    return {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in pinned_files(root)}


def prompt_versions(root: Path) -> dict[str, str]:
    out = {}
    for f in sorted((root / PINNED[0]).glob("*.md")):
        meta = yaml.safe_load(f.read_text(encoding="utf-8").split("---")[1])
        out[f.stem] = str(meta["version"])
    return out


def _require_clean(root: Path) -> None:
    dirty = _git(root, "status", "--porcelain", "--", *PINNED)
    if dirty:
        raise ReleaseError(f"uncommitted changes in pinned files:\n{dirty}")


def _gate(root: Path) -> list[dict[str, str]]:
    from lens.ops import gate

    checks = gate.run(root / "reports" / "eval")
    failed = [c for c in checks if c.status == "fail"]
    if failed:
        raise ReleaseError("eval gate fails:\n" + gate.render(failed))
    return [c.__dict__ for c in checks]


def create(name: str, root: Path = REPO_ROOT) -> Path:
    _require_clean(root)
    tag = f"release/{name}"
    if _git(root, "tag", "--list", tag):
        raise ReleaseError(f"{tag} already exists")
    manifest: dict[str, Any] = {
        "name": name,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": _git(root, "rev-parse", "HEAD"),
        "prompt_versions": prompt_versions(root),
        "gate": _gate(root),
        "files": file_hashes(root),
    }
    path = root / "releases" / f"{name}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1) + "\n")
    _git(root, "add", str(path.relative_to(root)))
    _git(root, "commit", "-m", f"release: {name}")
    _git(root, "tag", "-a", tag, "-m", f"release {name}")
    return path


def rollback(name: str, root: Path = REPO_ROOT) -> dict[str, Any]:
    _require_clean(root)
    tag = f"release/{name}"
    if not _git(root, "tag", "--list", tag):
        raise ReleaseError(f"no such release: {tag}")
    manifest = json.loads(_git(root, "show", f"{tag}:releases/{name}.json"))
    _git(root, "rm", "-r", "-q", "--ignore-unmatch", "--", *PINNED)  # files added after the release go too
    at_tag = _git(root, "ls-tree", "-r", "--name-only", tag, "--", *PINNED).splitlines()
    _git(root, "checkout", tag, "--", *at_tag)  # only what the release had: pinned paths may be newer
    got = file_hashes(root)
    if got != manifest["files"]:
        diff = sorted(set(got.items()) ^ set(manifest["files"].items()))
        raise ReleaseError(f"restored files do not match the {name} manifest: {diff[:5]}")
    _gate(root)
    # `git rm` and `git checkout <tag> -- paths` already staged the deletions and the restored files.
    if _git(root, "status", "--porcelain", "--", *PINNED):
        _git(root, "commit", "-m", f"revert(release): roll back prompts, config and eval reports to {name}")
    return {"rolled_back_to": name, "prompt_versions": manifest["prompt_versions"], "files": len(got)}


def main(argv: list[str]) -> int:
    cmd = argv[0]
    try:
        if cmd == "create":
            print(f"wrote {create(argv[1]).relative_to(REPO_ROOT)} and tagged release/{argv[1]}")
        elif cmd == "rollback":
            print(rollback(argv[1]))
        elif cmd == "list":
            print(_git(REPO_ROOT, "tag", "--list", "release/*", "--sort=-creatordate"))
    except ReleaseError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
