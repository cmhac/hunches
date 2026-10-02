from dataclasses import dataclass

from hunches.files import Taxonomy


@dataclass
class LabelMetrics:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    gold_count: int  # items whose gold set contains the label
    predicted_count: int


@dataclass
class Metrics:
    exact_match: float  # predicted set == gold set (plain accuracy in single mode)
    per_label: dict[str, LabelMetrics]
    macro_f1: float
    micro_f1: float
    disagreements: list[int]  # indices where predicted != gold
    n: int

    @classmethod
    def from_dict(cls, d: dict) -> "Metrics":
        """Inverse of dataclasses.asdict, for results stored as JSON."""
        per_label = {k: LabelMetrics(**v) for k, v in d["per_label"].items()}
        return cls(**{**d, "per_label": per_label})


def _ratio(num: float, den: float) -> float:
    # every ratio with a zero denominator is defined as 0
    return num / den if den else 0.0


def compute_metrics(
    gold: list[set[str]], predicted: list[set[str]], labels: list[str]
) -> Metrics:
    """Score predictions. `labels` is the full list including off_topic.

    Macro-F1 averages per-label F1 over labels that appear in gold or in the
    predictions; a label absent from both is undefined, not a zero.
    """
    per_label = {}
    for label in labels:
        tp = sum(label in g and label in p for g, p in zip(gold, predicted))
        fp = sum(label not in g and label in p for g, p in zip(gold, predicted))
        fn = sum(label in g and label not in p for g, p in zip(gold, predicted))
        precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
        per_label[label] = LabelMetrics(
            precision=precision,
            recall=recall,
            f1=_ratio(2 * precision * recall, precision + recall),
            tp=tp,
            fp=fp,
            fn=fn,
            gold_count=tp + fn,
            predicted_count=tp + fp,
        )
    disagreements = [i for i, (g, p) in enumerate(zip(gold, predicted)) if g != p]
    present = [m for m in per_label.values() if m.gold_count or m.predicted_count]
    tp, fp, fn = (
        sum(getattr(m, k) for m in per_label.values()) for k in ("tp", "fp", "fn")
    )
    return Metrics(
        exact_match=_ratio(len(gold) - len(disagreements), len(gold)),
        per_label=per_label,
        macro_f1=_ratio(sum(m.f1 for m in present), len(present)),
        micro_f1=_ratio(2 * tp, 2 * tp + fp + fn),
        disagreements=disagreements,
        n=len(gold),
    )


def target_value(metrics: Metrics, name: str) -> float:
    """`accuracy` and `exact_match` are the same number; the UI label differs by mode."""
    return {
        "accuracy": metrics.exact_match,
        "exact_match": metrics.exact_match,
        "macro_f1": metrics.macro_f1,
        "micro_f1": metrics.micro_f1,
    }[name]


def default_target_metric(taxonomy: Taxonomy) -> str:
    """Spec default when the user has not chosen: accuracy (single), macro_f1 (multi)."""
    return "accuracy" if taxonomy.mode == "single" else "macro_f1"
