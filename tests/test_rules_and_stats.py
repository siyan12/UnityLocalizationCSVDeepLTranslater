import pytest

from tests.fakes import FakeDeepLClient
from translator_core import is_skippable_source, process_rows, should_fill_cell


SOURCE_COL = "English(en)"
DE_COL = "German(de)"


@pytest.mark.parametrize(
    "source",
    [None, "", " \t\r\n ", "https://example.com/path", "www.example.com", "123", "12.5", "...?!"],
)
def test_non_translatable_sources_are_skipped(source):
    assert is_skippable_source(source)


@pytest.mark.parametrize("source", ["Level 12", "100% complete", "example.com", "Hello!"])
def test_meaningful_sources_are_not_skipped(source):
    assert not is_skippable_source(source)


@pytest.mark.parametrize(
    ("current", "preserve_existing", "expected"),
    [
        (None, True, True),
        ("", True, True),
        ("  ", True, True),
        ("Existing", True, False),
        ("Existing", False, True),
    ],
)
def test_existing_translation_fill_rule(current, preserve_existing, expected):
    assert should_fill_cell(current, preserve_existing) is expected


def test_skip_and_preserve_statistics_are_counted_without_api_calls():
    client = FakeDeepLClient(lambda text, kwargs: "Hallo")
    rows = [
        {SOURCE_COL: "", DE_COL: ""},
        {SOURCE_COL: "https://example.com", DE_COL: ""},
        {SOURCE_COL: "Hello", DE_COL: "Schon vorhanden"},
        {SOURCE_COL: "Translate me", DE_COL: ""},
    ]

    result, stats = process_rows(rows, SOURCE_COL, {DE_COL: "DE"}, client)

    assert result[2][DE_COL] == "Schon vorhanden"
    assert result[3][DE_COL] == "Hallo"
    assert stats == {
        "rows": 4,
        "translated_cells": 1,
        "skipped_existing": 1,
        "skipped_source_invalid": 2,
        "errors": 0,
        "failed_cells": [],
        "api_requests": 1,
        "cache_hits": 0,
    }
    assert len(client.calls) == 1


def test_overwrite_mode_replaces_existing_translation():
    client = FakeDeepLClient(lambda text, kwargs: "Neu")
    rows = [{SOURCE_COL: "New", DE_COL: "Alt"}]

    result, stats = process_rows(
        rows,
        SOURCE_COL,
        {DE_COL: "DE"},
        client,
        preserve_existing=False,
    )

    assert result[0][DE_COL] == "Neu"
    assert stats["translated_cells"] == 1
    assert stats["skipped_existing"] == 0
    assert len(client.calls) == 1
