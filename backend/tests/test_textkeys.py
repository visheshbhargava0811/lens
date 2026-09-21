from lens.nlp.textkeys import canonical_url, content_hash, is_near_duplicate, simhash64


def test_canonical_url_strips_tracking_fragment_and_slash() -> None:
    a = canonical_url("HTTP://WWW.Example.com/News/Story-1/?utm_source=x&id=7&fbclid=abc#top")
    b = canonical_url("https://www.example.com/News/Story-1?id=7")
    assert a == b == "https://www.example.com/News/Story-1?id=7"


def test_canonical_url_keeps_content_params_sorted() -> None:
    assert canonical_url("https://x.in/a?b=2&a=1") == "https://x.in/a?a=1&b=2"


def test_content_hash_ignores_case_and_whitespace_but_not_script() -> None:
    assert content_hash("Rain  in Delhi", None) == content_hash("rain in delhi", "")
    assert content_hash("दिल्ली में बारिश", None) != content_hash("Delhi mein baarish", None)


def test_simhash_near_duplicates_are_close_and_different_texts_far() -> None:
    wire = "Parliament passes the data protection amendment bill after a long debate, PTI reports"
    copy = "Parliament passes the data protection amendment bill after a long debate, reports PTI"
    other = "Monsoon rainfall in Kerala was 20 per cent above normal this week, officials said"
    assert is_near_duplicate(wire, copy, simhash64(wire), simhash64(copy), 16, 0.75)
    assert not is_near_duplicate(wire, other, simhash64(wire), simhash64(other), 16, 0.75)


def test_simhash_fits_signed_bigint() -> None:
    for t in ["a b c", "दिल्ली में भारी बारिश", "x" * 50]:
        assert -(2**63) <= simhash64(t) < 2**63


def test_indic_words_stay_whole() -> None:
    from lens.nlp.textkeys import _tokens

    assert _tokens("राज्य सरकार ने बजट मंज़ूर किया") == ["राज्य", "सरकार", "ने", "बजट", "मंज़ूर", "किया"]


def test_unrelated_hindi_and_marathi_headlines_are_not_near_duplicates() -> None:
    pairs = [
        (
            "गोरखपुर रेस्टोरेंट विवाद: 550 रुपये के बिल पर पुलिसकर्मियों और कर्मचारियों में कहासुनी, दारोगा लाइन हाजिर",
            "नोएडा में दो फूड रेस्टोरेंट पर लगा तीन लाख का जुर्माना, नियमों के उल्लंघन का लगा आरोप",
        ),
        (
            "ॲक्वा लाईनच्या मेट्रो स्थानकांत ज्येष्ठांची कसरत; उद्वाहक दूर असल्याने पायऱ्यांवरून उतरण्याची नामुष्की",
            "ट्रेनमध्ये गर्भवती महिलांना काय सुविधा मिळतात? तिकीट बुक करण्यापूर्वी जाणून घ्या",
        ),
    ]
    for a, b in pairs:
        assert not is_near_duplicate(a, b, simhash64(a), simhash64(b), 16, 0.75)


def test_identical_hindi_wire_copy_is_near_duplicate() -> None:
    a = "सुप्रीम कोर्ट ने अवैध निर्माण पर राज्य सरकारों से चार हफ्ते में रिपोर्ट मांगी (भाषा)"
    b = "सुप्रीम कोर्ट ने अवैध निर्माण पर राज्य सरकारों से चार हफ्ते में रिपोर्ट मांगी"
    assert is_near_duplicate(a, b, simhash64(a), simhash64(b), 16, 0.75)
