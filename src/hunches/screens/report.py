"""Rendering shared by the tuning (5) and test (6) screens: metrics summary, per-label table, label cells."""

from rich.text import Text
from textual.widgets import DataTable
from textual.widgets.data_table import ColumnKey

from hunches import metrics
from hunches.theme import label_text

OTHERS = [
    ("exact_match", "exact-match"),
    ("macro_f1", "macro-F1"),
    ("micro_f1", "micro-F1"),
]


def summary(m: metrics.Metrics, target_metric: str, target_score: float) -> str:
    """`accuracy 0.860 PASS n=50 macro-F1 0.85 ...`, leaving out the metric that is the target."""
    passed = metrics.target_value(m, target_metric) >= target_score
    badge = "[b reverse $success] PASS [/]" if passed else "[b reverse $error] FAIL [/]"
    line = f"[$text-muted]{target_metric}[/] [b #EEF1F5]{metrics.target_value(m, target_metric):.3f}[/] {badge} [$text-muted]n={m.n}[/]"
    for attr, name in OTHERS:
        if attr != target_metric and (attr, target_metric) != (
            "exact_match",
            "accuracy",
        ):
            line += f"  [$text-muted]{name}[/] {getattr(m, attr):.3f}"
    return line


def per_label_columns(table: DataTable) -> None:
    table.add_column("Label")
    for name in ("P", "R", "F1", "gold"):
        table.add_column(Text(name, justify="right"), width=6)


def fill_per_label(table: DataTable, names: list[str], m: metrics.Metrics) -> None:
    table.clear()
    for name, x in m.per_label.items():
        right = lambda v: Text(v, justify="right")
        table.add_row(
            label_text(names, name),
            right(f"{x.precision:.2f}"),
            right(f"{x.recall:.2f}"),
            right(f"{x.f1:.2f}"),
            right(str(x.gold_count)),
            key=name,
        )


def tags(names: list[str], labels: list[str] | set[str] | str) -> Text:
    """Label tags for a disagreement cell; `failed` (a call that errored) is bold red."""
    if labels == "failed":
        return Text("failed", style="bold #F2557A")
    return Text(", ").join(label_text(names, n) for n in sorted(labels))


def disagreement_columns(table: DataTable) -> None:
    table.add_column(
        "Text", key="text", width=20
    )  # a fixed width; fit_text_column resizes it
    table.add_column("Gold", width=15)
    table.add_column("Predicted", width=15)


def fit_text_column(table: DataTable) -> None:
    """DataTable has no flex column: give Text whatever the fixed columns leave."""
    table.columns[ColumnKey("text")].width = max(
        4, table.size.width - 2 * 3 - 15 - 15 - 2
    )


def clipped(text: str) -> Text:
    return Text(text.replace("\n", " "), no_wrap=True, overflow="ellipsis")
