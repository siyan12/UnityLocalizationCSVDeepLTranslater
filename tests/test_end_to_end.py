import csv
from types import SimpleNamespace

import translator_core
from tests.fakes import FakeDeepLClient


def test_folder_translation_end_to_end_preserves_csv_and_existing_values(
    tmp_path, monkeypatch
):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source = input_dir / "localization.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            ["Key", "Id", "Shared Comments", "English(en)", "German(de)"]
        )
        writer.writerow(["GREETING", "1", "Comma, quote, and newline", 'Hello, "friend"\nNext', ""])
        writer.writerow(["PRESERVED", "2", "Do not overwrite", "Existing source", "Vorhanden"])
        writer.writerow(["SKIPPED", "3", "URL stays empty", "https://example.com", ""])

    client = FakeDeepLClient(
        lambda text, kwargs: text.replace("Hello", "Hallo").replace("Next", "Weiter")
    )
    monkeypatch.setattr(
        translator_core,
        "deepl",
        SimpleNamespace(Translator=lambda api_key: client),
    )

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir)
    )

    output = output_dir / "localization.csv"
    with output.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert summary["status"] == "success"
    assert summary["rows"] == 3
    assert summary["translated_cells"] == 1
    assert summary["skipped_existing"] == 1
    assert summary["skipped_source_invalid"] == 1
    assert summary["errors"] == 0
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert rows[0]["Shared Comments"] == "Comma, quote, and newline"
    assert rows[0]["English(en)"] == 'Hello, "friend"\nNext'
    assert rows[0]["German(de)"] == 'Hallo, "friend"\nWeiter'
    assert rows[1]["German(de)"] == "Vorhanden"
    assert rows[2]["German(de)"] == ""
    assert len(client.calls) == 1
