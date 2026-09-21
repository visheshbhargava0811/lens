import pytest

from lens.ingest.triage import classify_news, detect_language, detect_wire


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Government releases draft rules for app-based cab services", "en"),
        ("राज्य सरकार ने नई मेट्रो लाइन के लिए बजट मंज़ूर किया", "hi"),
        ("राज्य सरकारकडून नव्या मेट्रो मार्गासाठी निधी मंजूर करण्यात आला आहे", "mr"),
        ("Iran America war ke baare mein batao", "hi-Latn"),
        ("Sarkar ne naye niyam jari kiye hai, logon ko kya fayda hoga", "hi-Latn"),
        ("சென்னையில் புதிய பேருந்து வழித்தடங்கள் அறிமுகம்", "ta"),
        ("নতুন মেট্রো লাইনের জন্য বাজেট অনুমোদন", "bn"),
        ("", "und"),
    ],
)
def test_detect_language(text: str, code: str) -> None:
    assert detect_language(text).code == code


def test_english_with_one_hindi_loanword_stays_english() -> None:
    assert detect_language("The sarkar announced a new scheme for farmers in Punjab today").code == "en"


def test_news_filter_drops_horoscopes_and_flags_opinion() -> None:
    assert classify_news("https://x.in/astrology/aaj-ka-rashifal-123", "आज का राशिफल").is_news is False
    assert classify_news("https://x.in/web-stories/foo", "Ten photos").is_news is False
    op = classify_news("https://x.in/opinion/columns/why-it-matters", "Why it matters")
    assert op.is_news and op.is_opinion
    assert classify_news("https://x.in/india/metro-budget", "Metro budget approved").reason is None


@pytest.mark.parametrize(
    ("byline", "title", "snippet", "agency"),
    [
        ("PTI", "Rain lashes Mumbai", None, "PTI"),
        (None, "Rain lashes Mumbai", "MUMBAI (PTI): Heavy rain lashed the city on Monday.", "PTI"),
        (None, "Rain lashes Mumbai", "Heavy rain lashed the city on Monday. - ANI", "ANI"),
        (None, "Rain lashes Mumbai", "मुंबई, (भाषा) शहर में भारी बारिश हुई।", "PTI"),
        ("Reuters staff", "Oil prices rise", None, "Reuters"),
        # False-positive guards: a person named Ani, a word containing "pti", an ordinary "ap".
        ("Ani Sharma", "Local elections", None, None),
        ("Staff reporter, with inputs from PTI", "Rain lashes Mumbai", None, "PTI"),
        ("Agencies (IANS)", "Rain lashes Mumbai", None, "IANS"),
        (None, "Ani Sharma wins local election", "Ani Sharma won by 300 votes.", None),
        (None, "Optimism grows in markets", "Receptive investors lifted shares.", None),
        (None, "Tap water supply restored", "The ap-proach road was repaired.", None),
    ],
)
def test_detect_wire(byline: str | None, title: str, snippet: str | None, agency: str | None) -> None:
    assert detect_wire(byline, title, snippet) == agency


def test_mixed_latin_prefix_devanagari_headline_is_hindi() -> None:
    assert detect_language("Mahendragarh-Narnaul News आज एक घंटा बिजली आपूर्ति रहेगी बंद").code == "hi"


def test_declared_language_breaks_hi_mr_ties_only() -> None:
    assert detect_language("दहा तलवारींसह गुन्हेगार गजाआड", declared="mr").code == "mr"
    # Clear textual evidence wins over a wrong declaration.
    assert detect_language("राज्य सरकार ने नई मेट्रो लाइन के लिए बजट मंज़ूर किया", declared="mr").code == "hi"
