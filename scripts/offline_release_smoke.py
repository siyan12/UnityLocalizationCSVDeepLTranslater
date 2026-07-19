"""Run a release smoke test with a local fake provider and a public sample CSV."""

from __future__ import annotations

import csv
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import translator_core  # noqa: E402


class OfflineTranslator:
    """DeepL-shaped deterministic fake; it never performs network I/O."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []

    def translate_text(self, text: object, **kwargs: object) -> object:
        self.calls.append((text, kwargs))

        def translate(value: str) -> SimpleNamespace:
            language = str(kwargs["target_lang"])
            return SimpleNamespace(text=f"[{language}] {value}")

        if isinstance(text, list):
            return [translate(str(value)) for value in text]
        return translate(str(text))


def run_smoke_test() -> None:
    sample = ROOT / "examples" / "offline_roundtrip_input.csv"
    if not sample.is_file():
        raise AssertionError(f"Release sample is missing: {sample}")

    fake = OfflineTranslator()
    original_deepl = translator_core.deepl
    try:
        translator_core.deepl = SimpleNamespace(Translator=lambda _api_key: fake)
        with tempfile.TemporaryDirectory(prefix="csvtranslator-release-") as temp_dir:
            work = Path(temp_dir)
            input_dir = work / "input"
            output_dir = work / "output"
            input_dir.mkdir()
            shutil.copy2(sample, input_dir / sample.name)

            summary = translator_core.run_translation_for_folder(
                "offline-fake-key",
                str(input_dir),
                str(output_dir),
            )
            output = output_dir / sample.name
            if summary["status"] != "success" or not output.is_file():
                raise AssertionError(f"Offline round trip failed: {summary}")

            with sample.open("r", encoding="utf-8-sig", newline="") as source_file:
                source_rows = list(csv.DictReader(source_file))
            with output.open("r", encoding="utf-8-sig", newline="") as output_file:
                output_rows = list(csv.DictReader(output_file))

            if len(source_rows) != len(output_rows):
                raise AssertionError("Round trip changed the CSV row count.")
            for before, after in zip(source_rows, output_rows):
                for column in ("Key", "Id", "Shared Comments", "English(en)"):
                    if before[column] != after[column]:
                        raise AssertionError(f"Round trip changed protected column {column!r}.")

            by_key = {row["Key"]: row for row in output_rows}
            if by_key["MULTILINE_HINT"]["German(de)"] != "Bereits übersetzt":
                raise AssertionError("An existing translation was overwritten.")
            if by_key["DOCS_LINK"]["German(de)"] or by_key["DOCS_LINK"]["Japanese(ja)"]:
                raise AssertionError("A URL-only source should remain untranslated.")
            welcome = by_key["WELCOME_PLAYER"]
            for column in ("German(de)", "Japanese(ja)"):
                if "<b>{playerName}</b>" not in welcome[column]:
                    raise AssertionError(f"Placeholders or tags were damaged in {column!r}.")
            if not fake.calls:
                raise AssertionError("The fake translation path was not exercised.")
            if summary["translated_cells"] != 5 or summary["errors"] != 0:
                raise AssertionError(f"Unexpected smoke-test summary: {summary}")
    finally:
        translator_core.deepl = original_deepl


def main() -> int:
    try:
        run_smoke_test()
    except Exception as error:
        print(f"Offline release smoke test failed: {error}", file=sys.stderr)
        return 1
    print("Offline release smoke test passed; no DeepL request was made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
