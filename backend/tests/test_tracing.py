import os

import pytest
from pydantic import SecretStr

from lens.core.settings import Settings
from lens.core.tracing import configure_tracing, tracing_smoke


def test_tracing_disabled_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    s = Settings(langsmith_tracing=True, langsmith_api_key=None, _env_file=None)
    assert configure_tracing(s) is False
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_tracing_enabled_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    s = Settings(langsmith_tracing=True, langsmith_api_key=SecretStr("x"), _env_file=None)
    assert configure_tracing(s) is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


def test_smoke_function_runs_untraced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    assert tracing_smoke("hi") == {"echo": "hi"}


@pytest.mark.live
def test_smoke_trace_reaches_langsmith() -> None:
    """Run with `make trace-smoke` once LANGSMITH_API_KEY is set in .env."""
    import asyncio
    import time
    import uuid

    from langsmith import Client

    from lens.core.settings import get_settings

    settings = get_settings()
    if not configure_tracing(settings):
        pytest.skip("LANGSMITH_TRACING/LANGSMITH_API_KEY not set")

    client = Client()
    run_id = uuid.uuid4()
    tracing_smoke("phase0", langsmith_extra={"client": client, "run_id": run_id})
    client.flush()

    project_id = str(client.read_project(project_name=settings.langsmith_project).id)
    for _ in range(20):  # ingestion is asynchronous on the LangSmith side
        try:
            # In langsmith 0.13 `client.runs` is async even on the sync Client.
            run = asyncio.run(
                client.runs.retrieve(
                    str(run_id), project_id=project_id, selects=["NAME", "OUTPUTS", "STATUS"]
                )
            )
            break
        except Exception:
            time.sleep(1.5)
    else:
        pytest.fail(f"run {run_id} did not appear in LangSmith project {settings.langsmith_project}")
    assert run.name == "lens.tracing_smoke"
    assert run.outputs == {"echo": "phase0"}
    print(f"trace ok: project={settings.langsmith_project} run_id={run_id}")
