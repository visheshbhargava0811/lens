"""LangSmith tracing setup.

The langsmith SDK reads LANGSMITH_TRACING / LANGSMITH_API_KEY / LANGSMITH_PROJECT
from the process environment, so settings are exported there at startup.
"""

import os

import langsmith
from langsmith import Client, traceable

from lens.core.settings import Settings


def configure_tracing(settings: Settings) -> bool:
    """Export tracing settings to the environment. Returns whether tracing is active."""
    enabled = settings.langsmith_tracing and settings.langsmith_api_key is not None
    os.environ["LANGSMITH_TRACING"] = "true" if enabled else "false"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key is not None:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    if enabled:
        from lens.guardrails.pii import mask_any

        # G-OUT-05: every run's inputs and outputs are masked on the client before they are sent,
        # including LangGraph's own tracer (it uses this global client).
        langsmith.configure(client=Client(hide_inputs=mask_any, hide_outputs=mask_any))
    return enabled


@traceable(name="lens.tracing_smoke", run_type="chain", tags=["graph:none", "smoke"])
def tracing_smoke(message: str) -> dict[str, str]:
    """Trivial traced function used to confirm traces reach LangSmith."""
    return {"echo": message}
