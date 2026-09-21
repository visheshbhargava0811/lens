import pytest

from lens.core.config_files import load_yaml


@pytest.mark.parametrize(
    "name", ["models.yaml", "retrieval.yaml", "clustering.yaml", "guardrails.yaml", "eval_gates.yaml"]
)
def test_config_files_parse(name: str) -> None:
    assert load_yaml(name)


def test_judge_tier_exists_separately_from_synthesis() -> None:
    tiers = load_yaml("models.yaml")["tiers"]
    assert {"synthesis", "judge", "analysis", "triage", "query_understanding"} <= set(tiers)
