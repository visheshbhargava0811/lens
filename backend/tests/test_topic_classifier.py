from lens.nlp.topic_classifier import classify


def test_classify() -> None:
    assert classify("Lok Sabha passes new bill") == "politics"
    assert classify("Kohli hits century as India beat Australia") == "sports"
    assert classify("Sensex falls 500 points") == "business"
    assert classify("ISRO launches Chandrayaan mission") == "science"
    assert classify("बिहार विधानसभा चुनाव: मतदान आज") == "politics"
    assert classify("आईपीएल में मुंबई की जीत") == "sports"
    assert classify("शेअर बाजार कोसळला") == "business"
    # Whole-word only: "over" and "pm" are not keywords; "ai" must not match inside "said".
    assert classify("He said the rain was over by 5 pm") is None


def test_prototype_assign() -> None:
    import numpy as np

    from lens.nlp.topic_embed import Prototypes

    p = Prototypes(["politics", "sports"], np.eye(3)[:2], mean=np.zeros(3))
    assert p.assign(np.array([1.0, 0.1, 0.0]), min_sim=0.5, min_margin=0.0) == "politics"
    assert p.assign(np.array([0.1, 1.0, 0.0]), min_sim=0.5, min_margin=0.0) == "sports"
    assert p.assign(np.array([0.1, 0.1, 1.0]), min_sim=0.5, min_margin=0.0) is None  # fits neither
    assert p.assign(np.array([1.0, 0.95, 0.0]), min_sim=0.5, min_margin=0.1) is None  # ambiguous
