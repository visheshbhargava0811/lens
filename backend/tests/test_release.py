"""docs/08: rollback re-pins prompts, config and eval reports in one command."""

import subprocess
from pathlib import Path

import pytest

from lens.ops import release


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(release, "_gate", lambda root: [])  # the gate has its own tests
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    skills = tmp_path / release.PINNED[0]
    skills.mkdir(parents=True)
    (skills / "ask_synthesis.md").write_text('---\nversion: "1.0"\n---\nCite every sentence.\n')
    (tmp_path / "config").mkdir()
    (tmp_path / "config/models.yaml").write_text("tiers: {ask_synthesis: {model: good}}\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_rollback_restores_prompts_and_config(repo: Path) -> None:
    release.create("r1", repo)
    assert "release/r1" in git(repo, "tag")
    prompt = repo / release.PINNED[0] / "ask_synthesis.md"
    prompt.write_text('---\nversion: "2.0"\n---\nBroken prompt.\n')
    (repo / "config/retrieval.yaml").write_text("tier1: {window_days: 1}\n")  # added after r1
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "bad change")

    out = release.rollback("r1", repo)
    assert out["prompt_versions"] == {"ask_synthesis": "1.0"}
    assert "Cite every sentence." in prompt.read_text()
    assert not (repo / "config/retrieval.yaml").exists()  # files added later are removed too
    assert "roll back" in git(repo, "log", "-1", "--format=%s")
    assert git(repo, "status", "--porcelain") == ""


def test_refuses_with_uncommitted_pinned_changes(repo: Path) -> None:
    release.create("r1", repo)
    (repo / "config/models.yaml").write_text("tiers: {}\n")
    with pytest.raises(release.ReleaseError, match="uncommitted"):
        release.rollback("r1", repo)
    with pytest.raises(release.ReleaseError, match="uncommitted"):
        release.create("r2", repo)


def test_unknown_or_duplicate_release_is_refused(repo: Path) -> None:
    release.create("r1", repo)
    with pytest.raises(release.ReleaseError, match="already exists"):
        release.create("r1", repo)
    with pytest.raises(release.ReleaseError, match="no such release"):
        release.rollback("nope", repo)
