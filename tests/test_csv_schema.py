import csv
import re
from types import SimpleNamespace

import pytest

import translator_core
from tests.fakes import FakeDeepLClient
from translator_core import CsvSchemaError, detect_language_columns, load_csv, write_csv


HEADERS = ["Key", "Id", "English(en)", "German(de)"]


def write_bytes(path, text, *, bom=False):
    prefix = b"\xef\xbb\xbf" if bom else b""
    path.write_bytes(prefix + text.encode("utf-8"))


@pytest.mark.parametrize("bom", [False, True])
def test_csv_round_trip_preserves_bom_structure_and_values(tmp_path, bom):
    source = tmp_path / "source.csv"
    output = tmp_path / "output.csv"
    write_bytes(
        source,
        'Key,Id,English(en),German(de)\r\n'
        'FIRST,1,"Hello, world","He said ""Hallo"""\r\n'
        'SECOND,2,"Line one\r\nLine two",Existing\r\n',
        bom=bom,
    )

    document = load_csv(str(source))
    write_csv(
        str(output),
        document.fieldnames,
        document.rows,
        preserve_utf8_bom=document.has_utf8_bom,
    )

    assert document.has_utf8_bom is bom
    assert document.fieldnames == HEADERS
    assert [row["Key"] for row in document.rows] == ["FIRST", "SECOND"]
    assert document.rows[0]["English(en)"] == "Hello, world"
    assert document.rows[0]["German(de)"] == 'He said "Hallo"'
    assert document.rows[1]["English(en)"] == "Line one\r\nLine two"
    assert output.read_bytes().startswith(b"\xef\xbb\xbf") is bom

    with output.open("r", encoding="utf-8-sig", newline="") as output_file:
        reader = csv.reader(output_file, strict=True)
        assert list(reader) == [HEADERS] + [
            [row[header] for header in HEADERS] for row in document.rows
        ]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "no header"),
        (",Id,English(en),German(de)\nK,1,Hello,\n", "empty header"),
        (
            "Key,Id,English(en),German(de),German(de)\nK,1,Hello,,\n",
            "duplicate header",
        ),
        ("Key,Id,English(en),German(de)\nK,1,Hello\n", "has 3 fields; expected 4"),
        (
            "Key,Id,English(en),German(de)\nK,1,Hello,,extra\n",
            "has 5 fields; expected 4",
        ),
    ],
)
def test_load_csv_rejects_malformed_structure(tmp_path, content, message):
    path = tmp_path / "invalid.csv"
    write_bytes(path, content)

    with pytest.raises(CsvSchemaError, match=message):
        load_csv(str(path))


@pytest.mark.parametrize("missing", ["English(en)"])
def test_required_columns_are_reported(missing):
    headers = [header for header in HEADERS if header != missing]

    with pytest.raises(CsvSchemaError, match=re.escape(missing)):
        detect_language_columns(headers, "English(en)")


def test_key_or_id_identity_column_is_accepted():
    assert detect_language_columns(
        ["Key", "English(en)", "German(de)"], "English(en)"
    )[1] == {"German(de)": "DE"}
    assert detect_language_columns(
        ["Id", "English(en)", "German(de)"], "English(en)"
    )[1] == {"German(de)": "DE"}


def test_missing_both_identity_columns_is_reported():
    with pytest.raises(CsvSchemaError, match="Key.*or.*Id"):
        detect_language_columns(["English(en)", "German(de)"], "English(en)")


def test_unsupported_language_column_is_not_silently_ignored():
    headers = HEADERS + ["Italian(it)"]

    with pytest.raises(CsvSchemaError, match=r"Unsupported language.*Italian\(it\)"):
        detect_language_columns(headers, "English(en)")


def test_comment_and_custom_metadata_columns_are_preserved_not_translated():
    headers = [
        "Key",
        "Id",
        "Shared Comments",
        "English(en)",
        "English(en) Comments",
        "German(de)",
        "German(de) Comments",
        "Custom Metadata",
        "Owner(dev)",
    ]

    source, targets = detect_language_columns(headers, "English(en)")

    assert source == "English(en)"
    assert targets == {"German(de)": "DE"}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([",,Hello,"], "non-empty 'Key' or a positive 'Id'"),
        (["A,1,Hello,", "A,2,Again,"], "duplicates 'Key'"),
        (["A,1,Hello,", "B,1,Again,"], "duplicates 'Id'"),
        (["A,not-a-number,Hello,"], "invalid 'Id'"),
    ],
)
def test_invalid_identifiers_are_rejected_before_deepl_call(tmp_path, monkeypatch, rows, message):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    csv_path = input_dir / "invalid.csv"
    write_bytes(csv_path, ",".join(HEADERS) + "\n" + "\n".join(rows) + "\n")

    client = FakeDeepLClient()
    monkeypatch.setattr(
        translator_core,
        "deepl",
        SimpleNamespace(Translator=lambda api_key: client),
    )
    logs = []

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key",
        str(input_dir),
        str(output_dir),
        logger=logs.append,
    )

    assert summary["files"] == 0
    assert summary["errors"] == 1
    assert client.calls == []
    assert not (output_dir / "invalid.csv").exists()
    assert any(message in line for line in logs)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "Key,Id,English(en),German(de)\nA,1,Hello\n",
            "has 3 fields; expected 4",
        ),
        (
            "Key,Id,English(en),German(de),Italian(it)\nA,1,Hello,,\n",
            "Unsupported language",
        ),
    ],
)
def test_other_schema_errors_also_stop_before_deepl_call(
    tmp_path, monkeypatch, content, message
):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    write_bytes(input_dir / "invalid.csv", content)
    client = FakeDeepLClient()
    monkeypatch.setattr(
        translator_core,
        "deepl",
        SimpleNamespace(Translator=lambda api_key: client),
    )
    logs = []

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir), logger=logs.append
    )

    assert summary["files"] == 0
    assert summary["errors"] == 1
    assert client.calls == []
    assert not (output_dir / "invalid.csv").exists()
    assert any(message in line for line in logs)


def test_empty_and_zero_ids_are_allowed_when_keys_are_present(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    write_bytes(
        input_dir / "new_entries.csv",
        ",".join(HEADERS) + "\nA,,Hello,\nB,0,Again,\nC,0,Third,\n",
    )
    client = FakeDeepLClient()
    monkeypatch.setattr(
        translator_core,
        "deepl",
        SimpleNamespace(Translator=lambda api_key: client),
    )

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir)
    )

    assert summary["files"] == 1
    assert summary["errors"] == 0
    assert len(client.calls) == 3
