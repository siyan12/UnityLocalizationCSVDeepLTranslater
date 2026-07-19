import csv
import threading
from types import SimpleNamespace

import translator_core


SOURCE_COL = "English(en)"
DE_COL = "German(de)"
FR_COL = "French(fr)"


class BatchFakeDeepLClient:
    """Small DeepL-shaped fake which records both scalar and batch requests."""

    def __init__(self, responder=None):
        self.responder = responder or (lambda text, kwargs: text)
        self.calls = []

    def translate_text(self, text, **kwargs):
        self.calls.append((text, kwargs))
        if isinstance(text, list):
            return [
                SimpleNamespace(text=self.responder(item, kwargs))
                for item in text
            ]
        return SimpleNamespace(text=self.responder(text, kwargs))


def install_fake_deepl(monkeypatch, client):
    monkeypatch.setattr(
        translator_core,
        "deepl",
        SimpleNamespace(Translator=lambda api_key: client),
    )


def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(headers)
        writer.writerows(rows)


def requested_texts(client):
    return [
        item
        for payload, _kwargs in client.calls
        for item in (payload if isinstance(payload, list) else [payload])
    ]


def test_same_target_texts_are_sent_in_one_batch():
    client = BatchFakeDeepLClient(lambda text, kwargs: f"{text}-DE")
    rows = [
        {SOURCE_COL: "One", DE_COL: ""},
        {SOURCE_COL: "Two", DE_COL: ""},
        {SOURCE_COL: "Three", DE_COL: ""},
    ]

    translated, stats = translator_core.process_rows(
        rows,
        SOURCE_COL,
        {DE_COL: "DE"},
        client,
    )

    assert len(client.calls) == 1
    payload, kwargs = client.calls[0]
    assert payload == ["One", "Two", "Three"]
    assert kwargs["target_lang"] == "DE"
    assert [row[DE_COL] for row in translated] == ["One-DE", "Two-DE", "Three-DE"]
    assert stats["translated_cells"] == 3


def test_batch_count_is_capped_at_fifty_texts():
    client = BatchFakeDeepLClient()
    rows = [
        {SOURCE_COL: f"Text {index}", DE_COL: ""}
        for index in range(51)
    ]

    translated, stats = translator_core.process_rows(
        rows, SOURCE_COL, {DE_COL: "DE"}, client
    )

    assert [len(payload) for payload, _ in client.calls] == [50, 1]
    assert stats["translated_cells"] == 51
    assert translated[-1][DE_COL] == "Text 50"


def test_folder_run_caches_duplicate_source_across_files(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    headers = ["Key", "Id", SOURCE_COL, DE_COL]
    write_csv(input_dir / "a.csv", headers, [["A", "1", "Hello", ""]])
    write_csv(input_dir / "b.csv", headers, [["B", "2", "Hello", ""]])
    client = BatchFakeDeepLClient(lambda text, kwargs: "Hallo")
    install_fake_deepl(monkeypatch, client)

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key",
        str(input_dir),
        str(output_dir),
    )

    assert summary["status"] == "success"
    assert summary["translated_cells"] == 2
    assert requested_texts(client) == ["Hello"]


def test_estimate_counts_targets_billable_and_unique_characters(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    headers = ["Key", "Id", SOURCE_COL, DE_COL, FR_COL]
    write_csv(
        input_dir / "a.csv",
        headers,
        [
            ["A", "1", "Hello", "", ""],
            ["B", "2", "World!", "Schon da", ""],
        ],
    )
    write_csv(
        input_dir / "b.csv",
        headers,
        [["C", "3", "Hello", "", ""]],
    )

    estimate = translator_core.estimate_translation_for_folder(str(input_dir))

    # Five eligible cells contain 26 source characters before caching. The
    # unique requests are Hello->DE, Hello->FR and World!->FR (16 characters).
    assert estimate["target_languages"] == 2
    assert estimate["characters"] == len("Hello") * 4 + len("World!")
    assert estimate["unique_characters"] == len("Hello") * 2 + len("World!")
    assert estimate["eligible_cells"] == 5
    assert estimate["unique_requests"] == 3


def test_cancelling_current_file_preserves_previous_output(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    write_csv(
        input_dir / "strings.csv",
        ["Key", "Id", SOURCE_COL, DE_COL],
        [["A", "1", "One", ""], ["B", "2", "Two", ""]],
    )
    output = output_dir / "strings.csv"
    previous = b"previous successful output"
    output.write_bytes(previous)
    cancel_event = threading.Event()

    def translate_then_cancel(text, kwargs):
        cancel_event.set()
        return f"{text}-DE"

    client = BatchFakeDeepLClient(translate_then_cancel)
    install_fake_deepl(monkeypatch, client)

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key",
        str(input_dir),
        str(output_dir),
        cancel_event=cancel_event,
    )

    assert summary["status"] == "cancelled"
    assert summary["cancelled"] is True
    assert output.read_bytes() == previous
    assert list(output_dir.glob(".*.tmp")) == []


def test_cancellation_during_atomic_flush_does_not_commit(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    write_csv(
        input_dir / "strings.csv",
        ["Key", "Id", SOURCE_COL, DE_COL],
        [["A", "1", "One", ""]],
    )
    output = output_dir / "strings.csv"
    previous = b"previous successful output"
    output.write_bytes(previous)
    cancel_event = threading.Event()
    client = BatchFakeDeepLClient(lambda text, kwargs: f"{text}-DE")
    install_fake_deepl(monkeypatch, client)
    real_fsync = translator_core.os.fsync

    def cancel_after_flush(file_descriptor):
        real_fsync(file_descriptor)
        cancel_event.set()

    monkeypatch.setattr(translator_core.os, "fsync", cancel_after_flush)

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key",
        str(input_dir),
        str(output_dir),
        cancel_event=cancel_event,
    )

    assert summary["status"] == "cancelled"
    assert output.read_bytes() == previous
    assert list(output_dir.glob(".*.tmp")) == []


def test_invalid_batch_result_type_is_rejected():
    client = BatchFakeDeepLClient(lambda text, kwargs: None)

    translated, stats = translator_core.process_rows(
        [{SOURCE_COL: "Hello", DE_COL: "Old"}],
        SOURCE_COL,
        {DE_COL: "DE"},
        client,
        preserve_existing=False,
    )

    assert translated[0][DE_COL] == "Old"
    assert stats["translated_cells"] == 0
    assert stats["errors"] == 1
    assert stats["failed_cells"][0]["error"] == (
        "DeepL returned an invalid translation response."
    )


def test_changed_input_after_estimate_is_not_sent(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source = input_dir / "strings.csv"
    write_csv(
        source,
        ["Key", "Id", SOURCE_COL, DE_COL],
        [["A", "1", "One", ""]],
    )
    estimate = translator_core.estimate_translation_for_folder(str(input_dir))
    write_csv(
        source,
        ["Key", "Id", SOURCE_COL, DE_COL],
        [["A", "1", "Changed source text", ""]],
    )
    client = BatchFakeDeepLClient()
    install_fake_deepl(monkeypatch, client)

    try:
        translator_core.run_translation_for_folder(
            "not-a-real-key",
            str(input_dir),
            str(output_dir),
            expected_input_snapshot=estimate["input_snapshot"],
        )
    except RuntimeError as error:
        assert "changed after the estimate" in str(error)
    else:
        raise AssertionError("changed input should require a new estimate")

    assert client.calls == []
