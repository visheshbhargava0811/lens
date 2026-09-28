"""Phase 8 acceptance (docs/12): the post-translation check G-OUT-06 catches deliberately corrupted entities
and numbers, in Hindi and Marathi, and lets faithful translations through."""

import pytest

from lens.core.config_files import load_yaml
from lens.guardrails.generation import check_translation

CFG = load_yaml("guardrails.yaml")["translation_check"]

GOOD = [
    (
        "hi",
        "Prime Minister Narendra Modi met Jaishankar in Delhi on Tuesday.",
        "प्रधानमंत्री नरेंद्र मोदी ने मंगलवार को दिल्ली में जयशंकर से मुलाकात की।",
    ),
    ("hi", "India beat Sri Lanka by 147 runs in Hangzhou.", "भारत ने हांगझोउ में श्रीलंका को 147 रनों से हराया।"),
    (
        "hi",
        "According to A2, the BJP and RBI officials met at ISRO.",
        "A2 के अनुसार, बीजेपी और आरबीआई के अधिकारी इसरो में मिले।",
    ),
    ("hi", "Rahul Gandhi said the Election Commission erred.", "राहुल गांधी ने कहा कि चुनाव आयोग ने गलती की।"),
    (
        "mr",
        "Chief Minister Devendra Fadnavis said 3,500 farmers in Pune got relief.",
        "मुख्यमंत्री देवेंद्र फडणवीस म्हणाले की पुण्यातील 3,500 शेतकऱ्यांना दिलासा मिळाला.",
    ),
    (
        "mr",
        "According to A1, Sharad Pawar met Uddhav Thackeray in Mumbai.",
        "A1 नुसार, शरद पवार यांनी मुंबईत उद्धव ठाकरे यांची भेट घेतली.",
    ),
]


@pytest.mark.parametrize(("lang", "src", "tr"), GOOD)
def test_faithful_translations_pass(lang: str, src: str, tr: str) -> None:
    res = check_translation([src], [tr], lang, CFG["skip_words"], CFG["aliases"], CFG["phrase_words"])
    assert res.passed, res.meta


CORRUPTED = [
    # (lang, source, corrupted translation, what must be flagged)
    ("hi", GOOD[0][1], GOOD[0][2].replace("मोदी", "गांधी"), "entity:"),  # a different person
    ("hi", GOOD[0][1], GOOD[0][2].replace("दिल्ली", "मुंबई"), "entity:"),  # a different place
    ("hi", GOOD[0][1], GOOD[0][2].replace("जयशंकर", "राजनाथ"), "entity:"),
    ("hi", GOOD[1][1], GOOD[1][2].replace("147", "174"), "number"),  # a changed number
    ("hi", GOOD[1][1], GOOD[1][2].replace("147 ", ""), "number"),  # a dropped number
    ("hi", GOOD[2][1], GOOD[2][2].replace("बीजेपी", "कांग्रेस"), "entity:"),  # a different party
    ("hi", GOOD[3][1], "राहुल गांधी: चुनाव आयोग ने गलती की।", "attribution"),  # "said" dropped
    ("mr", GOOD[4][1], GOOD[4][2].replace("फडणवीस", "शिंदे"), "entity:"),
    ("mr", GOOD[4][1], GOOD[4][2].replace("3,500", "35,000"), "number"),
    ("mr", GOOD[5][1], GOOD[5][2].replace("उद्धव ठाकरे", "राज ठाकरे"), "entity:"),
]


@pytest.mark.parametrize(("lang", "src", "tr", "flag"), CORRUPTED)
def test_corrupted_entities_and_numbers_are_caught(lang: str, src: str, tr: str, flag: str) -> None:
    res = check_translation([src], [tr], lang, CFG["skip_words"], CFG["aliases"], CFG["phrase_words"])
    assert not res.passed and res.action == "block"
    assert any(w.startswith(flag) for w in res.meta["why"]["0"]), res.meta
