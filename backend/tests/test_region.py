"""Story region for the Local tab (F-15): URL sections to a state, most specific section first."""

import pytest

from lens.nlp.region import story_region, url_region


@pytest.mark.parametrize(
    ("url", "state"),
    [
        ("https://www.bhaskar.com/local/mp/gwalior/news/land-case-139173069.html", "madhya-pradesh"),
        ("https://www.thehindu.com/news/national/tamil-nadu/some-story/article1.ece", "tamil-nadu"),
        ("https://www.amarujala.com/delhi-ncr/noida/some-story", "uttar-pradesh"),  # the city beats delhi-ncr
        ("https://www.esakal.com/marathwada/aurangabad/some-story", "maharashtra"),  # ambiguous city skipped
        ("https://www.hindustantimes.com/cities/lucknow-news/some-story", "uttar-pradesh"),
        ("https://www.aajtak.in/india/news/story/some-story", None),
        ("https://www.jagran.com/uttar-pradesh", None),  # the last part is the article, never a section
    ],
)
def test_url_region(url: str, state: str | None) -> None:
    assert url_region(url) == state


def test_story_needs_a_clear_majority_of_all_articles() -> None:
    up = "https://www.bhaskar.com/local/uttar-pradesh/kanpur/news/a.html"
    national = "https://www.aajtak.in/india/news/story/b"
    assert story_region([up, up, national]) == "uttar-pradesh"
    assert story_region([up, national, national]) is None  # a national story with one local copy
    assert story_region([up, "https://www.jagran.com/bihar/patna-c"]) is None  # split between two states
    assert story_region([]) is None
