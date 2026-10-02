from pytest import approx

from hunches.files import Label, Taxonomy
from hunches.metrics import compute_metrics, default_target_metric, target_value


def S(*labels):
    return set(labels)


def test_single_label_with_off_topic():
    # labels a, b, off_topic; gold a,a,b,b,off; predicted a,b,b,off,off
    # exact: items 0,2,4 match -> 3/5; disagreements 1 and 3
    # a: tp1 fp0 fn1 -> P 1, R 1/2, F1 2/3
    # b: tp1 fp1 fn1 -> P 1/2, R 1/2, F1 1/2
    # off_topic: tp1 fp1 fn0 -> P 1/2, R 1, F1 2/3
    # macro = (2/3 + 1/2 + 2/3) / 3 = 11/18; micro: tp3 fp2 fn2 -> 6/10
    m = compute_metrics(
        [S("a"), S("a"), S("b"), S("b"), S("off_topic")],
        [S("a"), S("b"), S("b"), S("off_topic"), S("off_topic")],
        ["a", "b", "off_topic"],
    )
    assert m.exact_match == approx(0.6)
    assert m.disagreements == [1, 3]
    a, b, off = m.per_label["a"], m.per_label["b"], m.per_label["off_topic"]
    assert (a.precision, a.recall, a.f1) == approx((1, 0.5, 2 / 3))
    assert (b.precision, b.recall, b.f1) == approx((0.5, 0.5, 0.5))
    assert (off.precision, off.recall, off.f1) == approx((0.5, 1, 2 / 3))
    assert (a.gold_count, b.gold_count, off.gold_count) == (2, 2, 1)
    assert (a.predicted_count, b.predicted_count, off.predicted_count) == (1, 2, 2)
    assert m.macro_f1 == approx(11 / 18)
    assert m.micro_f1 == approx(0.6)


def test_multi_label_partial_overlap():
    # labels x, y, z, off_topic; gold {x,y} {x} {z} {y,z}; predicted {x} {x,y} {z} {y}
    # exact: only item 2 -> 1/4; disagreements 0, 1, 3
    # x: tp2 fp0 fn0 -> F1 1
    # y: gold items 0,3; predicted 1,3 -> tp1 fp1 fn1 -> P 1/2, R 1/2, F1 1/2
    # z: gold 2,3; predicted 2 -> tp1 fp0 fn1 -> P 1, R 1/2, F1 2/3
    # off_topic: in neither gold nor predictions -> excluded from macro
    # macro = (1 + 1/2 + 2/3) / 3 = 13/18
    # micro: tp4 fp1 fn2 -> 8 / 11
    m = compute_metrics(
        [S("x", "y"), S("x"), S("z"), S("y", "z")],
        [S("x"), S("x", "y"), S("z"), S("y")],
        ["x", "y", "z", "off_topic"],
    )
    assert m.exact_match == approx(0.25)
    assert m.disagreements == [0, 1, 3]
    assert m.per_label["x"].f1 == approx(1)
    assert m.per_label["y"].f1 == approx(0.5)
    assert m.per_label["z"].precision == approx(1)
    assert m.per_label["z"].recall == approx(0.5)
    assert m.per_label["z"].f1 == approx(2 / 3)
    assert m.per_label["off_topic"].f1 == 0
    assert m.macro_f1 == approx(13 / 18)
    assert m.micro_f1 == approx(8 / 11)


def test_label_with_no_gold_examples():
    # labels a, b; gold {a} {a}; predicted {a} {b}; exact 1/2
    # a: tp1 fp0 fn1 -> P 1, R 1/2, F1 2/3
    # b: tp0 fp1 fn0 -> P 0, recall denominator is 0 -> R 0, F1 0
    # macro = (2/3 + 0) / 2 = 1/3; micro: tp1 fp1 fn1 -> 2/4
    m = compute_metrics([S("a"), S("a")], [S("a"), S("b")], ["a", "b"])
    b = m.per_label["b"]
    assert (b.precision, b.recall, b.f1, b.gold_count) == (0, 0, 0, 0)
    assert m.exact_match == approx(0.5)
    assert m.macro_f1 == approx(1 / 3)
    assert m.micro_f1 == approx(0.5)


def test_all_correct():
    # every set matches: exact 1, every present label P=R=F1=1, macro = micro = 1
    gold = [S("a"), S("a", "b"), S("off_topic")]
    m = compute_metrics(gold, [set(g) for g in gold], ["a", "b", "off_topic"])
    assert m.exact_match == 1
    assert m.disagreements == []
    assert m.macro_f1 == 1
    assert m.micro_f1 == 1


def test_off_topic_mix():
    # labels x, y, off_topic; gold {off} {x} {x,y}; predicted {off} {off} {x}
    # exact: item 0 only -> 1/3; disagreements 1, 2
    # x: gold 1,2; predicted 2 -> tp1 fn1 -> P 1, R 1/2, F1 2/3
    # y: gold 2; never predicted -> tp0 fn1 -> P 0, R 0, F1 0
    # off_topic: gold 0; predicted 0,1 -> tp1 fp1 -> P 1/2, R 1, F1 2/3
    # macro = (2/3 + 0 + 2/3) / 3 = 4/9; micro: tp2 fp1 fn2 -> 4/7
    m = compute_metrics(
        [S("off_topic"), S("x"), S("x", "y")],
        [S("off_topic"), S("off_topic"), S("x")],
        ["x", "y", "off_topic"],
    )
    assert m.exact_match == approx(1 / 3)
    assert m.disagreements == [1, 2]
    assert m.per_label["off_topic"].f1 == approx(2 / 3)
    assert m.macro_f1 == approx(4 / 9)
    assert m.micro_f1 == approx(4 / 7)


def test_empty_input_is_zero():
    m = compute_metrics([], [], ["a"])
    assert (m.exact_match, m.macro_f1, m.micro_f1, m.disagreements) == (0, 0, 0, [])


def test_target_value_and_default():
    m = compute_metrics([S("a"), S("a")], [S("a"), S("b")], ["a", "b"])
    assert target_value(m, "accuracy") == target_value(m, "exact_match") == 0.5
    assert target_value(m, "macro_f1") == approx(1 / 3)
    assert target_value(m, "micro_f1") == approx(0.5)
    labels = [Label(name="a")]
    assert default_target_metric(Taxonomy(mode="single", labels=labels)) == "accuracy"
    assert default_target_metric(Taxonomy(mode="multi", labels=labels)) == "macro_f1"
