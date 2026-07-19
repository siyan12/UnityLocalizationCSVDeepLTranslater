import re

import pytest

from tests.fakes import FakeDeepLClient
from translator_core import process_rows


TOKEN_RE = re.compile(r"__UL10N\d+_PH_\d{4}__")
SOURCE = "Hello <b>{name}</b>\r\nNext"
SOURCE_COL = "English(en)"
DE_COL = "German(de)"
FR_COL = "French(fr)"


def delete_first_token(text):
    return TOKEN_RE.sub("", text, count=1)


def test_valid_fake_translation_preserves_structure():
    client = FakeDeepLClient(lambda text, kwargs: text.replace("Hello", "Hallo").replace("Next", "Weiter"))
    rows = [{SOURCE_COL: SOURCE, DE_COL: ""}]

    result, stats = process_rows(rows, SOURCE_COL, {DE_COL: "DE"}, client)

    assert result[0][DE_COL] == "Hallo <b>{name}</b>\r\nWeiter"
    assert stats["translated_cells"] == 1
    assert stats["errors"] == 0
    assert len(client.calls) == 1
    _, kwargs = client.calls[0]
    assert kwargs["source_lang"] == "EN"
    assert kwargs["preserve_formatting"] is True
    assert kwargs["split_sentences"] == "nonewlines"


@pytest.mark.parametrize("initial", ["", "Old translation"])
def test_corrupted_translation_keeps_previous_cell(initial):
    logs = []
    client = FakeDeepLClient(lambda text, kwargs: delete_first_token(text))
    rows = [{SOURCE_COL: SOURCE, DE_COL: initial}]

    result, stats = process_rows(
        rows,
        SOURCE_COL,
        {DE_COL: "DE"},
        client,
        preserve_existing=False,
        logger=logs.append,
    )

    assert result[0][DE_COL] == initial
    assert stats["translated_cells"] == 0
    assert stats["errors"] == 1
    assert len(client.calls) == 1
    assert any("protected placeholder, tag, or line-break" in line for line in logs)
    assert SOURCE not in "\n".join(logs)


def test_one_target_can_succeed_while_another_is_rejected():
    def respond(text, kwargs):
        if kwargs["target_lang"] == "FR":
            return delete_first_token(text)
        return text.replace("Hello", "Hallo")

    client = FakeDeepLClient(respond)
    rows = [{SOURCE_COL: SOURCE, DE_COL: "", FR_COL: "Ancien"}]

    result, stats = process_rows(
        rows,
        SOURCE_COL,
        {DE_COL: "DE", FR_COL: "FR"},
        client,
        preserve_existing=False,
    )

    assert result[0][DE_COL].startswith("Hallo")
    assert result[0][FR_COL] == "Ancien"
    assert stats["translated_cells"] == 1
    assert stats["errors"] == 1


def test_invalid_response_is_not_cached():
    client = FakeDeepLClient(lambda text, kwargs: delete_first_token(text))
    rows = [
        {SOURCE_COL: SOURCE, DE_COL: ""},
        {SOURCE_COL: SOURCE, DE_COL: ""},
    ]

    result, stats = process_rows(rows, SOURCE_COL, {DE_COL: "DE"}, client)

    assert [row[DE_COL] for row in result] == ["", ""]
    assert stats["errors"] == 2
    # Duplicate work is sent once per task, but invalid output never enters the cache.
    assert len(client.calls) == 1


def test_valid_response_is_cached():
    client = FakeDeepLClient()
    rows = [
        {SOURCE_COL: SOURCE, DE_COL: ""},
        {SOURCE_COL: SOURCE, DE_COL: ""},
    ]

    _, stats = process_rows(rows, SOURCE_COL, {DE_COL: "DE"}, client)

    assert stats["translated_cells"] == 2
    assert len(client.calls) == 1


def test_empty_response_is_an_error_and_keeps_existing_text():
    client = FakeDeepLClient(lambda text, kwargs: "")
    rows = [{SOURCE_COL: "Hello", DE_COL: "Old translation"}]

    result, stats = process_rows(
        rows,
        SOURCE_COL,
        {DE_COL: "DE"},
        client,
        preserve_existing=False,
    )

    assert result[0][DE_COL] == "Old translation"
    assert stats["translated_cells"] == 0
    assert stats["errors"] == 1
    assert len(client.calls) == 1


def test_invalid_source_never_calls_translation_client():
    client = FakeDeepLClient()
    rows = [{SOURCE_COL: "Broken {name", DE_COL: ""}]

    result, stats = process_rows(rows, SOURCE_COL, {DE_COL: "DE"}, client)

    assert result[0][DE_COL] == ""
    assert stats["errors"] == 1
    assert client.calls == []
