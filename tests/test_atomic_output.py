import csv
from types import SimpleNamespace

import pytest

import translator_core
from tests.fakes import FakeDeepLClient


def install_fake_deepl(monkeypatch, client):
    monkeypatch.setattr(
        translator_core,
        "deepl",
        SimpleNamespace(Translator=lambda api_key: client),
    )


def write_input(path, headers, rows, *, bom=False):
    prefix = b"\xef\xbb\xbf" if bom else b""
    lines = [",".join(headers)] + [",".join(row) for row in rows]
    path.write_bytes(prefix + ("\n".join(lines) + "\n").encode("utf-8"))


def read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def assert_no_temp_files(output_dir):
    assert list(output_dir.glob(".*.tmp")) == []


def test_success_is_atomically_committed(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    write_input(
        input_dir / "strings.csv",
        ["Key", "Id", "English(en)", "German(de)"],
        [["HELLO", "1", "Hello", ""]],
        bom=True,
    )
    client = FakeDeepLClient(lambda text, kwargs: "Hallo")
    install_fake_deepl(monkeypatch, client)

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir)
    )

    output = output_dir / "strings.csv"
    assert summary["status"] == "success"
    assert summary["successful_files"] == 1
    assert summary["partial_files"] == 0
    assert summary["failed_files"] == 0
    assert read_rows(output)[0]["German(de)"] == "Hallo"
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert_no_temp_files(output_dir)


def test_partial_output_keeps_failed_cell_and_reports_it(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    headers = ["Key", "Id", "English(en)", "German(de)", "French(fr)"]
    write_input(
        input_dir / "strings.csv",
        headers,
        [["HELLO", "1", "Hello", "Alte", "Ancienne"]],
    )

    def respond(text, kwargs):
        return "" if kwargs["target_lang"] == "FR" else "Hallo"

    client = FakeDeepLClient(respond)
    install_fake_deepl(monkeypatch, client)

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key",
        str(input_dir),
        str(output_dir),
        overwrite_existing=True,
    )

    row = read_rows(output_dir / "strings.csv")[0]
    assert summary["status"] == "partial"
    assert summary["partial_files"] == 1
    assert summary["translated_cells"] == 1
    assert summary["errors"] == 1
    assert row["German(de)"] == "Hallo"
    assert row["French(fr)"] == "Ancienne"
    assert summary["failed_cells"] == [
        {
            "file": "strings.csv",
            "row": 2,
            "column": "French(fr)",
            "target_lang": "FR",
            "error": "Translation returned empty text.",
        }
    ]
    assert "Hello" not in repr(summary["failed_cells"])
    assert_no_temp_files(output_dir)


def test_provider_error_report_does_not_echo_localization_text(monkeypatch):
    sensitive_text = "Confidential quest ending"
    api_key_text = "paid-key-that-must-not-leak"

    def fail_with_echo(text, kwargs):
        raise RuntimeError(f"provider rejected: {text[:12]} using {api_key_text}")

    client = FakeDeepLClient(fail_with_echo)

    _, stats = translator_core.process_rows(
        [{"English(en)": sensitive_text, "German(de)": ""}],
        "English(en)",
        {"German(de)": "DE"},
        client,
    )

    assert stats["errors"] == 1
    assert sensitive_text not in repr(stats["failed_cells"])
    assert sensitive_text[:12] not in repr(stats["failed_cells"])
    assert api_key_text not in repr(stats["failed_cells"])
    assert stats["failed_cells"][0]["error"].endswith("(RuntimeError).")


def test_all_cell_failures_do_not_replace_previous_output(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    write_input(
        input_dir / "strings.csv",
        ["Key", "Id", "English(en)", "German(de)"],
        [["HELLO", "1", "Hello", ""]],
    )
    output = output_dir / "strings.csv"
    previous = b"previous successful output"
    output.write_bytes(previous)
    client = FakeDeepLClient(lambda text, kwargs: "")
    install_fake_deepl(monkeypatch, client)

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir)
    )

    assert summary["status"] == "failed"
    assert summary["files"] == 0
    assert summary["failed_files"] == 1
    assert summary["failed_cells"][0]["row"] == 2
    assert output.read_bytes() == previous
    assert_no_temp_files(output_dir)


@pytest.mark.parametrize("failure_point", ["fsync", "replace"])
def test_atomic_write_failure_preserves_previous_output_and_cleans_temp(
    tmp_path, monkeypatch, failure_point
):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    write_input(
        input_dir / "strings.csv",
        ["Key", "Id", "English(en)", "German(de)"],
        [["HELLO", "1", "Hello", ""]],
    )
    output = output_dir / "strings.csv"
    previous = b"previous successful output"
    output.write_bytes(previous)
    client = FakeDeepLClient(lambda text, kwargs: "Hallo")
    install_fake_deepl(monkeypatch, client)

    def fail(*args, **kwargs):
        raise OSError(f"simulated {failure_point} failure")

    monkeypatch.setattr(translator_core.os, failure_point, fail)

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir)
    )

    assert summary["status"] == "failed"
    assert summary["files"] == 0
    assert summary["failed_files"] == 1
    assert summary["translated_cells"] == 0
    assert output.read_bytes() == previous
    assert_no_temp_files(output_dir)


def test_temp_cleanup_failure_is_reported(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    write_input(
        input_dir / "strings.csv",
        ["Key", "Id", "English(en)", "German(de)"],
        [["HELLO", "1", "Hello", ""]],
    )
    client = FakeDeepLClient(lambda text, kwargs: "Hallo")
    install_fake_deepl(monkeypatch, client)
    monkeypatch.setattr(
        translator_core.os,
        "fsync",
        lambda file_descriptor: (_ for _ in ()).throw(OSError("simulated write failure")),
    )
    monkeypatch.setattr(
        translator_core.os,
        "unlink",
        lambda path: (_ for _ in ()).throw(PermissionError("simulated cleanup failure")),
    )
    logs = []

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir), logger=logs.append
    )

    assert summary["status"] == "failed"
    assert any("Temporary CSV cleanup failed (PermissionError)" in line for line in logs)
    assert "Hello" not in "\n".join(logs)
    assert list(output_dir.glob(".*.tmp"))


def test_interruption_cleans_temp_without_replacing_output(tmp_path, monkeypatch):
    output = tmp_path / "strings.csv"
    previous = b"previous successful output"
    output.write_bytes(previous)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(translator_core.os, "replace", interrupt)

    with pytest.raises(KeyboardInterrupt):
        translator_core.write_csv_atomic(
            str(output),
            ["Key", "Id", "English(en)", "German(de)"],
            [{"Key": "A", "Id": "1", "English(en)": "Hello", "German(de)": "Hallo"}],
        )

    assert output.read_bytes() == previous
    assert_no_temp_files(tmp_path)


def test_mixed_success_and_file_failure_has_partial_batch_status(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    write_input(
        input_dir / "good.csv",
        ["Key", "Id", "English(en)", "German(de)"],
        [["HELLO", "1", "Hello", ""]],
    )
    write_input(
        input_dir / "bad.csv",
        ["Key", "Id", "English(en)", "German(de)"],
        [["BROKEN", "2", "Hello"]],
    )
    client = FakeDeepLClient(lambda text, kwargs: "Hallo")
    install_fake_deepl(monkeypatch, client)

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir)
    )

    assert summary["status"] == "partial"
    assert summary["successful_files"] == 1
    assert summary["failed_files"] == 1
    assert summary["files"] == 1
    assert (output_dir / "good.csv").exists()
    assert not (output_dir / "bad.csv").exists()


def test_no_input_files_has_failed_status(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    client = FakeDeepLClient()
    install_fake_deepl(monkeypatch, client)

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir)
    )

    assert summary["status"] == "failed"
    assert summary["files"] == 0
    assert client.calls == []
