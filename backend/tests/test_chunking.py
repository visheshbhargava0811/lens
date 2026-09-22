import numpy as np
import pytest

from lens.nlp.chunking import analyzed_text, chunk_article, recursive_chunks, semantic_chunks, sentence_spans
from lens.nlp.embed import HashEmbedder


def _texts(text: str) -> list[str]:
    return [text[a:b] for a, b in sentence_spans(text)]


def test_splits_on_danda_and_latin_punctuation() -> None:
    text = "सरकार ने बजट पेश किया। विपक्ष ने विरोध किया॥ Markets rose. Did they hold?  Yes!"
    assert _texts(text) == [
        "सरकार ने बजट पेश किया।",
        "विपक्ष ने विरोध किया॥",
        "Markets rose.",
        "Did they hold?",
        "Yes!",
    ]


def test_abbreviations_do_not_split() -> None:
    assert _texts("Dr. Singh met Govt. officials. Then Rs. 5 crore was released.") == [
        "Dr. Singh met Govt. officials.",
        "Then Rs. 5 crore was released.",
    ]


def test_offsets_point_back_into_the_text() -> None:
    text = "पहला वाक्य। दूसरा वाक्य है।\n\nThird paragraph here. And more."
    for c in recursive_chunks(text, max_chars=20) + semantic_chunks(
        text, lambda s: HashEmbedder().encode(list(s)).dense
    ):
        assert text[c.start : c.end] == c.text


def test_snippet_articles_are_one_chunk_with_exact_offsets() -> None:
    [c] = chunk_article("Metro budget approved", "The cabinet approved funds. More details soon.", None)
    assert c.text == analyzed_text("Metro budget approved", "The cabinet approved funds. More details soon.", None)
    assert (c.start, c.end) == (0, len(c.text))


def test_semantic_chunks_split_on_topic_change() -> None:
    text = "Rain floods Mumbai streets. Rain floods Mumbai trains. Budget cuts school funds. Budget cuts school jobs."
    chunks = semantic_chunks(text, lambda s: HashEmbedder().encode(list(s)).dense, pct=50, min_sents=2)
    assert [c.text for c in chunks] == [
        "Rain floods Mumbai streets. Rain floods Mumbai trains.",
        "Budget cuts school funds. Budget cuts school jobs.",
    ]


def test_hash_embedder_is_normalized_and_deterministic() -> None:
    e = HashEmbedder().encode(["a b c", "a b c", "x y z"])
    assert np.allclose(np.linalg.norm(e.dense, axis=1), 1.0)
    assert float(e.dense[0] @ e.dense[1]) == pytest.approx(1.0) and float(e.dense[0] @ e.dense[2]) < 0.5
