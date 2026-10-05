from hunches.models import price_label


def test_price_label_plain_model():
    assert (
        price_label("anthropic:claude-haiku-4-5")
        == "$1.00 in / $5.00 out per 1M tokens"
    )


def test_price_label_matches_by_prefix_rule():
    # the snapshot has no claude-sonnet-5-5 id; the claude-sonnet-5* rule covers it
    assert (
        price_label("anthropic:claude-sonnet-5-5")
        == "$2.00 in / $10.00 out per 1M tokens"
    )


def test_price_label_tiered_names_the_threshold_in_words():
    assert price_label("openai:gpt-6-sol") == (
        "$2.00 in / $10.00 out per 1M tokens (higher above 272K prompt tokens)"
    )


def test_price_label_embedding_has_input_price_only():
    assert price_label("openai:text-embedding-3-small") == "$0.02 in per 1M tokens"


def test_price_label_unknown_is_never_zero():
    assert price_label("openai:no-such-model") == "no price: cost will show ?"
    assert price_label("nonsense") == "no price: cost will show ?"


def test_recommended_models_exist_in_pydantic_ai_known_lists():
    # doubles as the "re-verify the recommended IDs" check from spec 002
    from hunches.models import known_models
    from hunches.system import RECOMMENDED

    known = known_models()
    for rec in RECOMMENDED.values():
        assert rec["assistant"] in known
        assert rec["classifier"] in known


def test_embedding_list_holds_openai_small():
    from hunches.models import known_models

    assert "openai:text-embedding-3-small" in known_models(embedding=True)


def test_rows_filter_by_provider_and_mark_recommended(monkeypatch):
    from hunches import models

    monkeypatch.setattr(
        models,
        "known_models",
        lambda embedding=False: [
            "anthropic:claude-haiku-4-5",
            "openai:gpt-6-sol",
            "openai:no-such-model",
            "gateway/openai:gpt-6-sol",
        ],
    )
    rows = models.model_rows("openai")
    assert [r.model for r in rows] == ["openai:gpt-6-sol", "openai:no-such-model"]
    assert [r.recommended for r in rows] == [True, False]
    assert rows[0].price.startswith("$2.00 in / $10.00 out")
    assert rows[1].price == "no price: cost will show ?"
    assert [r.model for r in models.model_rows("anthropic")] == [
        "anthropic:claude-haiku-4-5"
    ]


def test_rows_flag_deprecated(monkeypatch):
    from types import SimpleNamespace

    from hunches import models

    monkeypatch.setattr(models, "known_models", lambda embedding=False: ["openai:old"])
    monkeypatch.setattr(
        models,
        "_info",
        lambda model: SimpleNamespace(
            deprecated=True, get_prices=lambda now: SimpleNamespace(input_mtok=None)
        ),
    )
    assert models.model_rows("openai")[0].deprecated is True


def test_snapshot_date_is_the_library_timestamp():
    from genai_prices import data_snapshot

    from hunches.models import snapshot_date

    stamp = data_snapshot.get_snapshot().timestamp
    assert snapshot_date() == f"{stamp.year:04d}-{stamp.month:02d}-{stamp.day:02d}"
