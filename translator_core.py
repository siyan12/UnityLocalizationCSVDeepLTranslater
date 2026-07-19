#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translator_core.py

核心翻译引擎：封装 DeepL API 测试、CSV 翻译（含批量文件夹处理）与工具函数。
供 gui_app.py 调用；也可单独导入使用。

约定：
- 输入目录：./input
- 输出目录：./output
- 批量处理 input 目录下所有 .csv 文件，翻译后输出到 output 目录，文件名不变
- 默认仅填充空单元格（可配置是否覆盖）

依赖：
- pip install deepl
"""

import os
import re
import csv
import json
import tempfile
import warnings
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional, Sequence, Callable

try:
    import deepl  # pip install deepl
except ImportError:
    deepl = None


# 语言映射（与原 translate.py 保持一致）
LANG_HEADER_TO_DEEPL = {
    "Chinese (Simplified)(zh)": "ZH",
    "Chinese (Traditional)(zh-Hant)": "ZH-HANT",
    "English(en)": "EN",  # source
    "French(fr)": "FR",
    "German(de)": "DE",
    "Japanese(ja)": "JA",
    "Korean(ko)": "KO",
    "Polish(pl)": "PL",
    "Portuguese(pt)": "PT-PT",
    "Russian(ru)": "RU",
    "Spanish(es)": "ES",
    "Turkish(tr)": "TR",
}

# Standard-looking Unity locale headers that this version cannot translate.
# Unknown custom column names are preserved because Unity allows arbitrary CSV columns.
KNOWN_UNSUPPORTED_LANGUAGE_HEADERS = {
    "Arabic(ar)",
    "Bulgarian(bg)",
    "Czech(cs)",
    "Danish(da)",
    "Dutch(nl)",
    "Estonian(et)",
    "Finnish(fi)",
    "Greek(el)",
    "Hungarian(hu)",
    "Indonesian(id)",
    "Italian(it)",
    "Latvian(lv)",
    "Lithuanian(lt)",
    "Norwegian(nb)",
    "Romanian(ro)",
    "Slovak(sk)",
    "Slovenian(sl)",
    "Swedish(sv)",
    "Ukrainian(uk)",
}

KEY_COL = "Key"
ID_COL = "Id"
DEFAULT_SOURCE_COL = "English(en)"

URL_RE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)
ONLY_PUNCT_OR_SPACE_RE = re.compile(r"^[\W_]+$", re.UNICODE)
ONLY_DIGITS_RE = re.compile(r"^\d+(\.\d+)?$")

PRINTF_RE = re.compile(
    r"%(?:\([^)]+\)|\d+\$)?[-+#0 ']*(?:\d+|\*)?(?:\.(?:\d+|\*))?"
    r"(?:hh|h|ll|l|L|z|j|t)?[diuoxXfFeEgGaAcrspn%]"
)
DOLLAR_PLACEHOLDER_RE = re.compile(r"\$\d+")
ESCAPED_LINEBREAK_RE = re.compile(r"\\(?:r\\n|n|r)")
TAG_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9:_-]*")
VOID_TAG_NAMES = {"br", "sprite", "space", "quad", "page", "img", "hr"}
TOKEN_PREFIX_TEMPLATE = "__UL10N{generation}_PH_"
TOKEN_SUFFIX = "__"
FAILURE_LOG_LIMIT = 100
FATAL_PROVIDER_CATEGORIES = {"authentication", "quota", "invalid_request"}
MAX_BATCH_TEXTS = 50
# Keep headroom below DeepL's 128 KiB total request limit for JSON and options.
MAX_BATCH_TEXT_BYTES = 120 * 1024

Logger = Callable[[str], None]

POSSIBLE_SECRET_PATTERNS = (
    re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}:fx(?!\w)"),
    re.compile(r"(?i)(DeepL-Auth-Key\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:deepl[_-]?)?api[_-]?key\s*[:=]\s*)[^\s,;]+"),
)


def safe_error_message(error: BaseException, secret: str = "") -> str:
    """Return an error description with known and key-shaped secrets removed."""
    message = str(error)
    if secret:
        message = message.replace(secret, "[REDACTED]")
    for pattern in POSSIBLE_SECRET_PATTERNS:
        message = pattern.sub(
            lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]",
            message,
        )
    return message


def _safe_cell_error_message(error: BaseException) -> str:
    """Return only controlled messages; arbitrary exceptions may echo private cell text."""
    if isinstance(error, (StructureValidationError, CellTranslationError)):
        return safe_error_message(error)
    if isinstance(error, TranslationProviderError):
        return str(error)
    return f"Cell processing failed ({error.__class__.__name__})."


class StructureValidationError(ValueError):
    """Protected localization structure is malformed or changed."""


class CsvSchemaError(ValueError):
    """The input CSV cannot be processed without risking structural data loss."""


class TranslationProviderError(RuntimeError):
    """A provider failure expressed as a safe, actionable user message."""

    def __init__(self, message: str, category: str):
        super().__init__(message)
        self.category = category


class TranslationCancelled(RuntimeError):
    """An orderly user cancellation; the current file must not be committed."""


class CellTranslationError(ValueError):
    """A safe, cell-scoped failure that may be shown without source text."""


@dataclass(frozen=True)
class ProviderErrorClassification:
    category: str
    retryable: bool
    user_message: str


@dataclass(frozen=True)
class CsvDocument:
    """Validated CSV content plus encoding details needed for a safe round trip."""

    rows: List[Dict[str, str]]
    fieldnames: List[str]
    has_utf8_bom: bool

    def __iter__(self):
        # Preserve the historical ``rows, fieldnames = load_csv(...)`` API.
        yield self.rows
        yield self.fieldnames


StructuralPart = Tuple[int, int, str, str]


def _find_braced_end(text: str, start: int) -> Optional[int]:
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _find_tag_end(text: str, start: int) -> Optional[int]:
    index = start + 1
    quote = ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                quote = ""
        elif char in ('"', "'"):
            quote = char
        elif char == ">":
            return index + 1
        index += 1
    return None


def _tag_event(raw: str) -> Optional[Tuple[str, str]]:
    inner = raw[1:-1].strip()
    if not inner or inner.startswith(("!", "?")):
        return None
    if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", inner):
        return "open", "color"
    closing = inner.startswith("/")
    if closing:
        inner = inner[1:].lstrip()
    match = TAG_NAME_RE.match(inner)
    if not match:
        return None
    name = match.group(0).lower()
    if closing:
        return "close", name
    if inner.rstrip().endswith("/") or name in VOID_TAG_NAMES:
        return "void", name
    return "open", name


def _scan_structural_parts(text: str) -> List[StructuralPart]:
    """Scan protected structures once, preserving nested brace expressions."""
    parts: List[StructuralPart] = []
    index = 0
    while index < len(text):
        start = index
        if text.startswith("\r\n", index):
            parts.append((start, start + 2, "linebreak", "\r\n"))
            index += 2
            continue
        if text[index] in "\r\n":
            parts.append((start, start + 1, "linebreak", text[index]))
            index += 1
            continue
        escaped_linebreak = ESCAPED_LINEBREAK_RE.match(text, index)
        if escaped_linebreak:
            index = escaped_linebreak.end()
            parts.append((start, index, "linebreak", escaped_linebreak.group(0)))
            continue
        if text.startswith("{{", index):
            escaped_end = text.find("}}", index + 2)
            end = escaped_end + 2 if escaped_end >= 0 else start + 2
            parts.append((start, end, "brace", text[start:end]))
            index = end
            continue
        if text.startswith("}}", index):
            parts.append((start, start + 2, "brace", "}}"))
            index += 2
            continue
        if text[index] == "{":
            end = _find_braced_end(text, index)
            if end is None:
                raise StructureValidationError("Unbalanced opening brace in source text.")
            parts.append((start, end, "brace", text[start:end]))
            index = end
            continue
        if text[index] == "}":
            raise StructureValidationError("Unbalanced closing brace in source text.")
        if text[index] == "<":
            end = _find_tag_end(text, index)
            if end is not None:
                raw = text[start:end]
                if _tag_event(raw) is not None:
                    parts.append((start, end, "tag", raw))
                    index = end
                    continue
        printf_match = PRINTF_RE.match(text, index)
        if (
            printf_match
            and printf_match.group(0).startswith("% ")
            and printf_match.end() < len(text)
            and text[printf_match.end()].isalpha()
        ):
            printf_match = None
        if printf_match:
            index = printf_match.end()
            parts.append((start, index, "placeholder", printf_match.group(0)))
            continue
        dollar_match = DOLLAR_PLACEHOLDER_RE.match(text, index)
        if dollar_match:
            index = dollar_match.end()
            parts.append((start, index, "placeholder", dollar_match.group(0)))
            continue
        index += 1
    return parts


def _validate_tag_nesting(parts: Sequence[StructuralPart]) -> None:
    stack: List[str] = []
    for _, _, kind, raw in parts:
        if kind != "tag":
            continue
        event = _tag_event(raw)
        if event is None:
            continue
        event_type, name = event
        if event_type == "open":
            stack.append(name)
        elif event_type == "close":
            if not stack or stack[-1] != name:
                raise StructureValidationError(
                    f"Invalid rich-text tag nesting near </{name}>."
                )
            stack.pop()
    if stack:
        raise StructureValidationError(
            f"Unclosed rich-text tag <{stack[-1]}> in source text."
        )


def _structure_signature(
    text: str,
) -> Tuple[Counter[Tuple[str, Tuple[str, ...]]], Tuple[str, ...], Tuple[Tuple[str, Tuple[str, ...]], ...]]:
    parts = _scan_structural_parts(text)
    _validate_tag_nesting(parts)
    placeholders: Counter[Tuple[str, Tuple[str, ...]]] = Counter()
    tags: List[str] = []
    linebreaks: List[Tuple[str, Tuple[str, ...]]] = []
    tag_stack: List[str] = []
    for _, _, kind, raw in parts:
        if kind == "tag":
            tags.append(raw)
            event = _tag_event(raw)
            if event:
                event_type, name = event
                if event_type == "open":
                    tag_stack.append(name)
                elif event_type == "close":
                    tag_stack.pop()
        elif kind == "linebreak":
            linebreaks.append((raw, tuple(tag_stack)))
        else:
            placeholders[(raw, tuple(tag_stack))] += 1
    return placeholders, tuple(tags), tuple(linebreaks)


def ensure_directories(input_dir: str, output_dir: str) -> None:
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)


def _validate_headers(fieldnames: List[str]) -> None:
    if not fieldnames:
        raise CsvSchemaError("CSV is empty or has no header row.")

    empty_positions = [str(index) for index, name in enumerate(fieldnames, start=1) if not name.strip()]
    if empty_positions:
        raise CsvSchemaError(
            "CSV contains empty header names at column(s): " + ", ".join(empty_positions) + "."
        )

    duplicate_headers = sorted(name for name, count in Counter(fieldnames).items() if count > 1)
    if duplicate_headers:
        raise CsvSchemaError(
            "CSV contains duplicate header name(s): " + ", ".join(repr(name) for name in duplicate_headers) + "."
        )


def _validate_identifier_values(rows: List[Dict[str, str]]) -> None:
    seen_keys: Dict[str, int] = {}
    seen_ids: Dict[int, int] = {}
    for row_number, row in enumerate(rows, start=2):
        key = row.get(KEY_COL, "").strip()
        raw_id = row.get(ID_COL, "").strip()
        numeric_id = 0

        if raw_id:
            try:
                numeric_id = int(raw_id)
            except ValueError as error:
                raise CsvSchemaError(
                    f"Row {row_number} has an invalid 'Id' value; expected a non-negative integer."
                ) from error
            if numeric_id < 0:
                raise CsvSchemaError(
                    f"Row {row_number} has an invalid 'Id' value; expected a non-negative integer."
                )

        if not key and numeric_id == 0:
            raise CsvSchemaError(
                f"Row {row_number} must have a non-empty 'Key' or a positive 'Id'."
            )

        if key:
            if key in seen_keys:
                raise CsvSchemaError(
                    f"Row {row_number} duplicates 'Key' value from row {seen_keys[key]}."
                )
            seen_keys[key] = row_number

        # Unity uses an empty or zero Id for new entries, so only assigned Ids are unique.
        if numeric_id > 0:
            if numeric_id in seen_ids:
                raise CsvSchemaError(
                    f"Row {row_number} duplicates 'Id' value from row {seen_ids[numeric_id]}."
                )
            seen_ids[numeric_id] = row_number


def load_csv(path: str) -> CsvDocument:
    """Read UTF-8 CSV strictly and retain whether the input used a UTF-8 BOM."""
    try:
        with open(path, "rb") as raw_file:
            has_utf8_bom = raw_file.read(3) == b"\xef\xbb\xbf"

        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, strict=True)
            try:
                fieldnames = next(reader)
            except StopIteration as error:
                raise CsvSchemaError("CSV is empty or has no header row.") from error

            _validate_headers(fieldnames)
            rows: List[Dict[str, str]] = []
            for record_number, values in enumerate(reader, start=2):
                if len(values) != len(fieldnames):
                    raise CsvSchemaError(
                        f"CSV record {record_number} (ending at physical line {reader.line_num}) "
                        f"has {len(values)} fields; expected {len(fieldnames)}."
                    )
                rows.append(dict(zip(fieldnames, values)))
    except UnicodeDecodeError as error:
        raise CsvSchemaError("CSV must be UTF-8 encoded, with or without a UTF-8 BOM.") from error
    except csv.Error as error:
        raise CsvSchemaError(f"Malformed CSV near physical line {getattr(reader, 'line_num', '?')}: {error}") from error

    return CsvDocument(rows=rows, fieldnames=fieldnames, has_utf8_bom=has_utf8_bom)


def write_csv(
    path: str,
    fieldnames: List[str],
    rows: List[Dict[str, Any]],
    preserve_utf8_bom: bool = True,
) -> None:
    encoding = "utf-8-sig" if preserve_utf8_bom else "utf-8"
    with open(path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def write_csv_atomic(
    path: str,
    fieldnames: List[str],
    rows: List[Dict[str, Any]],
    preserve_utf8_bom: bool = True,
    cleanup_logger: Optional[Logger] = None,
    cancel_event: Optional[Any] = None,
) -> None:
    """Write a CSV beside its destination and atomically commit it when complete."""
    output_dir = os.path.dirname(os.path.abspath(path))
    filename = os.path.basename(path)
    encoding = "utf-8-sig" if preserve_utf8_bom else "utf-8"
    file_descriptor, temp_path = tempfile.mkstemp(
        prefix=f".{filename}.",
        suffix=".tmp",
        dir=output_dir,
    )
    committed = False
    try:
        temp_file = os.fdopen(file_descriptor, "w", encoding=encoding, newline="")
        file_descriptor = -1
        with temp_file:
            writer = csv.DictWriter(
                temp_file,
                fieldnames=fieldnames,
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()
            for row in rows:
                _check_cancelled(cancel_event)
                writer.writerow(row)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        _check_cancelled(cancel_event)
        os.replace(temp_path, path)
        committed = True
    finally:
        # Includes normal write errors and interruption during an orderly shutdown.
        if file_descriptor >= 0:
            try:
                os.close(file_descriptor)
            except OSError:
                pass
        if not committed:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                cleanup_message = (
                    "Temporary CSV cleanup failed "
                    f"({cleanup_error.__class__.__name__}); manual removal may be required: "
                    f"{os.path.basename(temp_path)}"
                )
                if cleanup_logger:
                    cleanup_logger(cleanup_message)
                else:
                    warnings.warn(cleanup_message, RuntimeWarning, stacklevel=2)


def detect_language_columns(fieldnames: List[str], source_col: str) -> Tuple[str, Dict[str, str]]:
    _validate_headers(fieldnames)
    if KEY_COL not in fieldnames and ID_COL not in fieldnames:
        raise CsvSchemaError(
            "Missing Unity Localization identity column: CSV must contain 'Key' or 'Id'."
        )
    if source_col not in fieldnames:
        raise CsvSchemaError(f"Source language column '{source_col}' not found in CSV headers.")
    if source_col != DEFAULT_SOURCE_COL:
        raise CsvSchemaError(
            f"Unsupported source language column: '{source_col}'. "
            f"This version only supports '{DEFAULT_SOURCE_COL}' as the source."
        )

    unsupported = [header for header in fieldnames if header in KNOWN_UNSUPPORTED_LANGUAGE_HEADERS]
    if unsupported:
        raise CsvSchemaError(
            "Unsupported language column(s): " + ", ".join(repr(name) for name in unsupported)
            + ". Remove them or add an explicit DeepL language mapping before translating."
        )

    targets: Dict[str, str] = {}
    for h in fieldnames:
        if h in (KEY_COL, ID_COL, source_col):
            continue
        code = LANG_HEADER_TO_DEEPL.get(h)
        if code:
            targets[h] = code
    if not targets:
        raise CsvSchemaError("No supported target language columns were found in CSV headers.")
    return source_col, targets


def is_skippable_source(text: str) -> bool:
    if text is None:
        return True
    t = text.strip()
    if not t:
        return True
    if URL_RE.match(t):
        return True
    if ONLY_DIGITS_RE.match(t):
        return True
    if ONLY_PUNCT_OR_SPACE_RE.match(t):
        return True
    return False


def tokenize_placeholders(text: str) -> Tuple[str, Dict[str, str]]:
    parts = _scan_structural_parts(text)
    _validate_tag_nesting(parts)
    mapping: Dict[str, str] = {}
    generation = 0
    prefix = TOKEN_PREFIX_TEMPLATE.format(generation=generation)
    while prefix in text:
        generation += 1
        prefix = TOKEN_PREFIX_TEMPLATE.format(generation=generation)

    chunks: List[str] = []
    cursor = 0
    for token_index, (start, end, _, raw) in enumerate(parts):
        chunks.append(text[cursor:start])
        token = f"{prefix}{token_index:04d}{TOKEN_SUFFIX}"
        mapping[token] = raw
        chunks.append(token)
        cursor = end
    chunks.append(text[cursor:])
    return "".join(chunks), mapping


def _validate_translation_tokens(text: str, mapping: Dict[str, str]) -> None:
    if not mapping:
        return
    first_token = next(iter(mapping))
    prefix = first_token.rsplit("_PH_", 1)[0] + "_PH_"
    token_re = re.compile(re.escape(prefix) + r"\d{4}" + re.escape(TOKEN_SUFFIX))
    actual = Counter(token_re.findall(text))
    expected = Counter(mapping.keys())
    if actual != expected:
        raise StructureValidationError(
            "Translation changed protected placeholder, tag, or line-break tokens."
        )


def detokenize_placeholders(text: str, mapping: Dict[str, str]) -> str:
    _validate_translation_tokens(text, mapping)
    if not mapping:
        return text
    token_re = re.compile("|".join(re.escape(token) for token in mapping))
    return token_re.sub(lambda match: mapping[match.group(0)], text)


def validate_translated_structure(source: str, translated: str) -> None:
    """Reject translated text whose protected structure differs from the source."""
    source_placeholders, source_tags, source_linebreaks = _structure_signature(source)
    translated_placeholders, translated_tags, translated_linebreaks = _structure_signature(translated)
    if translated_placeholders != source_placeholders:
        raise StructureValidationError(
            "Translation changed placeholder or brace structure."
        )
    if translated_tags != source_tags:
        raise StructureValidationError("Translation changed rich-text tag structure.")
    if translated_linebreaks != source_linebreaks:
        raise StructureValidationError("Translation changed line-break structure.")


def _exception_status_code(error: BaseException) -> Optional[int]:
    for name in ("http_status_code", "status_code", "status"):
        value = getattr(error, name, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def classify_provider_error(error: BaseException) -> ProviderErrorClassification:
    """Classify provider failures without exposing provider messages or cell text."""
    name = error.__class__.__name__.lower()
    status = _exception_status_code(error)

    if "authorization" in name or "authentication" in name or status in (401, 403):
        return ProviderErrorClassification(
            "authentication",
            False,
            "DeepL authentication failed. Check or replace the API Key.",
        )
    if "quota" in name or status == 456:
        return ProviderErrorClassification(
            "quota",
            False,
            "DeepL quota is exhausted. Check account usage or cost-control limits.",
        )
    if "toomanyrequests" in name or "rate" in name or status == 429:
        return ProviderErrorClassification(
            "rate_limit",
            True,
            "DeepL remained rate-limited after automatic retries. Wait and try again.",
        )
    if (
        isinstance(error, (TimeoutError, ConnectionError))
        or "timeout" in name
        or "connection" in name
    ):
        retryable = getattr(error, "should_retry", True) is not False
        return ProviderErrorClassification(
            "network",
            retryable,
            (
                "A temporary network error persisted. Check the connection and try again."
                if retryable
                else "The network request failed. Check proxy, TLS, and connection settings."
            ),
        )
    if status is not None and status >= 500:
        return ProviderErrorClassification(
            "service",
            True,
            "DeepL remained unavailable after automatic retries. Try again later.",
        )
    if getattr(error, "should_retry", False) is True:
        return ProviderErrorClassification(
            "service",
            True,
            "DeepL remained unavailable after automatic retries. Try again later.",
        )
    if isinstance(error, (TypeError, ValueError)) or (
        status is not None and 400 <= status < 500
    ):
        return ProviderErrorClassification(
            "invalid_request",
            False,
            "DeepL rejected the request parameters. Check language columns and settings.",
        )
    return ProviderErrorClassification(
        "unexpected",
        False,
        f"Unexpected translation provider error ({error.__class__.__name__}).",
    )


def translate_texts(
    translator: Any,
    texts: Sequence[str],
    target_lang: str,
) -> List[str]:
    """Translate one API batch; the official SDK owns transient HTTP retries."""
    try:
        result = translator.translate_text(
            list(texts),
            target_lang=target_lang,
            source_lang="EN",
            preserve_formatting=True,
            split_sentences="nonewlines",
            formality="default",
        )
        results = result if isinstance(result, (list, tuple)) else [result]
        if len(results) != len(texts):
            raise CellTranslationError("DeepL returned an unexpected translation count.")
        translated: List[str] = []
        for item in results:
            if not hasattr(item, "text") or not isinstance(item.text, str):
                raise CellTranslationError(
                    "DeepL returned an invalid translation response."
                )
            translated.append(item.text)
        return translated
    except CellTranslationError:
        raise
    except Exception as error:
        classification = classify_provider_error(error)
        raise TranslationProviderError(
            classification.user_message,
            classification.category,
        ) from error


def translate_text(translator: Any, text: str, target_lang: str) -> str:
    """Backward-compatible single-text wrapper around batched translation."""
    return translate_texts(translator, [text], target_lang)[0]


def _check_cancelled(cancel_event: Optional[Any]) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TranslationCancelled("Translation cancelled by user.")


def _translation_batches(items: Sequence[Tuple[Tuple[str, str], str]]):
    batch: List[Tuple[Tuple[str, str], str]] = []
    byte_count = 0
    for item in items:
        # JSON encoding accounts for quotes, backslashes and control characters.
        item_bytes = len(json.dumps(item[1], ensure_ascii=False).encode("utf-8")) + 1
        if item_bytes > MAX_BATCH_TEXT_BYTES:
            if batch:
                yield batch
                batch = []
                byte_count = 0
            yield [item]
            continue
        if batch and (
            len(batch) >= MAX_BATCH_TEXTS
            or byte_count + item_bytes > MAX_BATCH_TEXT_BYTES
        ):
            yield batch
            batch = []
            byte_count = 0
        batch.append(item)
        byte_count += item_bytes
    if batch:
        yield batch


def should_fill_cell(current_value: Any, preserve_existing: bool) -> bool:
    if not preserve_existing:
        return True
    if current_value is None:
        return True
    if str(current_value).strip() == "":
        return True
    return False


def estimate_translation_for_folder(
    input_dir: str,
    source_col: str = DEFAULT_SOURCE_COL,
    overwrite_existing: bool = False,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """Scan input without contacting DeepL and estimate task size safely."""
    estimate = {
        "files": 0,
        "eligible_cells": 0,
        "unique_requests": 0,
        "characters": 0,
        "unique_characters": 0,
        "target_languages": 0,
        "errors": [],
        "input_snapshot": {},
    }
    unique_requests: Dict[Tuple[str, str], int] = {}
    languages = set()
    if not os.path.isdir(input_dir):
        return estimate

    all_files = sorted(
        filename
        for filename in os.listdir(input_dir)
        if filename.lower().endswith(".csv")
        and os.path.isfile(os.path.join(input_dir, filename))
    )
    for filename in all_files:
        _check_cancelled(cancel_event)
        try:
            document = load_csv(os.path.join(input_dir, filename))
            rows, fieldnames = document
            source, targets_map = detect_language_columns(fieldnames, source_col)
            _validate_identifier_values(rows)
            estimate["files"] += 1
            for row in rows:
                source_text = row.get(source, "")
                if is_skippable_source(source_text):
                    continue
                try:
                    tokenized, _ = tokenize_placeholders(source_text)
                except StructureValidationError:
                    continue
                for header, target_lang in targets_map.items():
                    if not should_fill_cell(row.get(header, ""), not overwrite_existing):
                        continue
                    text = str(source_text)
                    billable_characters = len(tokenized)
                    estimate["eligible_cells"] += 1
                    estimate["characters"] += billable_characters
                    languages.add(target_lang)
                    unique_requests.setdefault(
                        (text, target_lang), billable_characters
                    )
                _check_cancelled(cancel_event)
        except (CsvSchemaError, OSError) as error:
            estimate["errors"].append(
                {"file": filename, "error": safe_error_message(error)}
            )

    estimate["unique_requests"] = len(unique_requests)
    estimate["unique_characters"] = sum(unique_requests.values())
    estimate["target_languages"] = len(languages)
    estimate["input_snapshot"] = _input_csv_snapshot(input_dir)
    return estimate


def _input_csv_snapshot(input_dir: str) -> Dict[str, Tuple[int, int]]:
    if not os.path.isdir(input_dir):
        return {}
    snapshot: Dict[str, Tuple[int, int]] = {}
    for filename in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir, filename)
        if filename.lower().endswith(".csv") and os.path.isfile(path):
            stat = os.stat(path)
            snapshot[filename] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def process_rows(
    rows: List[Dict[str, Any]],
    source_col: str,
    targets_map: Dict[str, str],
    translator: Any,
    preserve_existing: bool = True,
    logger: Optional[Logger] = None,
    translation_cache: Optional[Dict[Tuple[str, str], str]] = None,
    cancel_event: Optional[Any] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cache = translation_cache if translation_cache is not None else {}
    stats = {
        "rows": len(rows),
        "translated_cells": 0,
        "skipped_existing": 0,
        "skipped_source_invalid": 0,
        "errors": 0,
        "failed_cells": [],
        "api_requests": 0,
        "cache_hits": 0,
    }
    new_rows = [dict(row) for row in rows]
    pending_by_language: Dict[str, Dict[Tuple[str, str], Tuple[str, str, Dict[str, str]]]] = {}
    cell_work: List[Tuple[int, str, str, Tuple[str, str]]] = []

    for idx, row in enumerate(new_rows, start=1):
        _check_cancelled(cancel_event)
        source_text = row.get(source_col, "")
        if is_skippable_source(source_text):
            stats["skipped_source_invalid"] += 1
            continue

        try:
            tokenized, mapping = tokenize_placeholders(source_text)
        except StructureValidationError as error:
            for header in targets_map:
                if should_fill_cell(row.get(header, ""), preserve_existing):
                    safe_error = _safe_cell_error_message(error)
                    stats["errors"] += 1
                    stats["failed_cells"].append(
                        {
                            "row": idx + 1,
                            "column": header,
                            "target_lang": targets_map[header],
                            "error": f"Invalid source structure: {safe_error}",
                        }
                    )
                    if logger:
                        logger(
                            f"  -> FAILED for '{header}': "
                            f"invalid source structure ({safe_error})"
                        )
                else:
                    stats["skipped_existing"] += 1
            continue

        for header, target_lang in targets_map.items():
            current_value = row.get(header, "")
            if not should_fill_cell(current_value, preserve_existing):
                stats["skipped_existing"] += 1
                continue

            key_cache = (str(source_text), target_lang)
            cell_work.append((idx - 1, header, target_lang, key_cache))
            if key_cache not in cache:
                pending_by_language.setdefault(target_lang, {}).setdefault(
                    key_cache, (tokenized, str(source_text), mapping)
                )

    failures: Dict[Tuple[str, str], str] = {}
    for target_lang, pending in pending_by_language.items():
        items = [(key, data[0]) for key, data in pending.items()]
        for batch in _translation_batches(items):
            _check_cancelled(cancel_event)
            if (
                len(batch) == 1
                and len(json.dumps(batch[0][1], ensure_ascii=False).encode("utf-8")) + 1
                > MAX_BATCH_TEXT_BYTES
            ):
                failures[batch[0][0]] = "Source text is too large for a safe DeepL request."
                continue
            try:
                translated_batch = translate_texts(
                    translator, [tokenized for _, tokenized in batch], target_lang
                )
                stats["api_requests"] += 1
                if logger:
                    logger(f"Translated API batch: {len(batch)} text(s) to {target_lang}.")
                for (key_cache, _), translated in zip(batch, translated_batch):
                    tokenized, source_text, mapping = pending[key_cache]
                    try:
                        detok = detokenize_placeholders(translated, mapping)
                        if str(detok).strip() == "":
                            raise StructureValidationError("Translation returned empty text.")
                        validate_translated_structure(source_text, detok)
                        cache[key_cache] = detok
                    except Exception as error:
                        failures[key_cache] = _safe_cell_error_message(error)
            except Exception as error:
                if isinstance(error, TranslationProviderError) and error.category in FATAL_PROVIDER_CATEGORIES:
                    raise
                safe_error = _safe_cell_error_message(error)
                for key_cache, _ in batch:
                    failures[key_cache] = safe_error

    for row_index, header, target_lang, key_cache in cell_work:
        _check_cancelled(cancel_event)
        if key_cache in cache:
            new_rows[row_index][header] = cache[key_cache]
            stats["translated_cells"] += 1
            if key_cache not in pending_by_language.get(target_lang, {}):
                stats["cache_hits"] += 1
        else:
            safe_error = failures.get(key_cache, "Cell processing failed (RuntimeError).")
            stats["errors"] += 1
            stats["failed_cells"].append(
                {
                    "row": row_index + 2,
                    "column": header,
                    "target_lang": target_lang,
                    "error": safe_error,
                }
            )
            if logger:
                logger(f"  -> FAILED for '{header}': {safe_error}")

    return new_rows, stats


def test_api_key(api_key: str) -> Tuple[bool, str]:
    """
    Test whether the DeepL API Key is valid.
    Return (success, message)
    """
    if deepl is None:
        return False, "deepl library not installed. Please run: pip install deepl"

    if not api_key:
        return False, "API Key not provided."

    try:
        translator = deepl.Translator(api_key)
        # Simple request: translate a short phrase
        res = translator.translate_text("Hello", target_lang="DE")
        ok = hasattr(res, "text")
        return (True, "API Key is valid, successfully connected to DeepL.") if ok else (False, "API connection issue.")
    except Exception as error:
        classification = classify_provider_error(error)
        return False, classification.user_message


def run_translation_for_folder(
    api_key: str,
    input_dir: str = "input",
    output_dir: str = "output",
    source_col: str = DEFAULT_SOURCE_COL,
    overwrite_existing: bool = False,
    logger: Optional[Logger] = None,
    cancel_event: Optional[Any] = None,
    expected_input_snapshot: Optional[Dict[str, Tuple[int, int]]] = None,
) -> Dict[str, Any]:
    """
    批量翻译 input_dir 下所有 .csv 文件，输出到 output_dir。
    logger: 可选的回调函数，用于输出进度日志。
    返回兼容的计数，并附带 status、文件结果与不含本地化文本的 failed_cells 清单。
    """
    def log(msg: str) -> None:
        if logger:
            logger(msg)

    ensure_directories(input_dir, output_dir)

    if deepl is None:
        raise RuntimeError("deepl library not installed. Please run: pip install deepl")

    if not api_key:
        raise RuntimeError("Missing DeepL API Key.")

    if (
        expected_input_snapshot is not None
        and _input_csv_snapshot(input_dir) != expected_input_snapshot
    ):
        raise RuntimeError(
            "Input CSV files changed after the estimate. Review the files and start again."
        )

    translator = deepl.Translator(api_key)

    # 收集文件
    all_files = sorted([
        f for f in os.listdir(input_dir)
        if f.lower().endswith(".csv") and os.path.isfile(os.path.join(input_dir, f))
    ])

    summary = {
        "status": "failed",
        "files": 0,
        "successful_files": 0,
        "partial_files": 0,
        "failed_files": 0,
        "rows": 0,
        "translated_cells": 0,
        "skipped_existing": 0,
        "skipped_source_invalid": 0,
        "errors": 0,
        "failed_cells": [],
        "file_results": [],
        "provider_error_category": None,
        "fatal_error": "",
        "cancelled": False,
        "cancelled_file": "",
        "api_requests": 0,
        "cache_hits": 0,
    }

    if not all_files:
        log("No CSV files found in input directory. Please add files and try again.")
        return summary

    log(f"Found {len(all_files)} CSV files, starting...")
    translation_cache: Dict[Tuple[str, str], str] = {}
    for idx, filename in enumerate(all_files, start=1):
        in_path = os.path.join(input_dir, filename)
        out_path = os.path.join(output_dir, filename)

        log(f"[{idx}/{len(all_files)}] Processing file: {filename}")
        stats: Optional[Dict[str, Any]] = None
        try:
            _check_cancelled(cancel_event)
            document = load_csv(in_path)
            rows, fieldnames = document
            source, targets_map = detect_language_columns(fieldnames, source_col)
            _validate_identifier_values(rows)

            new_rows, stats = process_rows(
                rows,
                source,
                targets_map,
                translator,
                preserve_existing=not overwrite_existing,
                logger=log,
                translation_cache=translation_cache,
                cancel_event=cancel_event,
            )

            _check_cancelled(cancel_event)

            failed_cells = [
                {"file": filename, **failure}
                for failure in stats["failed_cells"]
            ]
            if failed_cells and stats["translated_cells"] == 0:
                failure_reason = "All requested cell translations failed; no output committed."
                log(f" - Status: FAILED; {failure_reason}")
                summary["failed_files"] += 1
                summary["errors"] += stats["errors"]
                summary["failed_cells"].extend(failed_cells)
                summary["file_results"].append(
                    {
                        "file": filename,
                        "status": "failed",
                        "rows": stats["rows"],
                        "translated_cells": 0,
                        "errors": stats["errors"],
                        "failed_cells": failed_cells,
                        "error": failure_reason,
                    }
                )
                continue

            file_status = "partial" if failed_cells else "success"
            write_csv_atomic(
                out_path,
                fieldnames,
                new_rows,
                preserve_utf8_bom=document.has_utf8_bom,
                cleanup_logger=log,
                cancel_event=cancel_event,
            )

            file_result = {
                "file": filename,
                "status": file_status,
                "rows": stats["rows"],
                "translated_cells": stats["translated_cells"],
                "errors": stats["errors"],
                "failed_cells": failed_cells,
            }

            # Logs & summary
            log(f" - Status: {file_status.upper()}; Rows: {stats['rows']}, "
                f"Translated cells: {stats['translated_cells']}, "
                f"Skipped invalid sources: {stats['skipped_source_invalid']}, Errors: {stats['errors']}"
                + (f", Preserved existing: {stats['skipped_existing']}" if not overwrite_existing else ""))

            summary["files"] += 1
            if file_status == "success":
                summary["successful_files"] += 1
            else:
                summary["partial_files"] += 1
            summary["rows"] += stats["rows"]
            summary["translated_cells"] += stats["translated_cells"]
            summary["skipped_existing"] += stats["skipped_existing"]
            summary["skipped_source_invalid"] += stats["skipped_source_invalid"]
            summary["errors"] += stats["errors"]
            summary["api_requests"] += stats["api_requests"]
            summary["cache_hits"] += stats["cache_hits"]
            summary["failed_cells"].extend(failed_cells)
            summary["file_results"].append(file_result)
        except TranslationCancelled:
            summary["cancelled"] = True
            summary["cancelled_file"] = filename
            log(
                f" - Status: CANCELLED; current file was not committed: {filename}"
            )
            break
        except Exception as e:
            provider_error = e if isinstance(e, TranslationProviderError) else None
            safe_error = (
                str(provider_error)
                if provider_error
                else safe_error_message(e, api_key)
            )
            failed_cells = (
                [{"file": filename, **failure} for failure in stats["failed_cells"]]
                if stats else []
            )
            log(f" - Status: FAILED; no output committed: {safe_error}")
            summary["failed_files"] += 1
            summary["errors"] += (stats["errors"] if stats else 0) + 1
            summary["failed_cells"].extend(failed_cells)
            file_result = {
                "file": filename,
                "status": "failed",
                "rows": stats["rows"] if stats else 0,
                "translated_cells": 0,
                "errors": (stats["errors"] if stats else 0) + 1,
                "failed_cells": failed_cells,
                "error": safe_error,
            }
            if provider_error:
                file_result["provider_error_category"] = provider_error.category
            summary["file_results"].append(file_result)
            if (
                provider_error
                and provider_error.category in FATAL_PROVIDER_CATEGORIES
            ):
                summary["provider_error_category"] = provider_error.category
                summary["fatal_error"] = safe_error
                log("Batch stopped because this provider error cannot succeed on retry.")
                break

    if summary["cancelled"]:
        summary["status"] = "cancelled"
    elif summary["failed_files"] == 0 and summary["partial_files"] == 0:
        summary["status"] = "success"
    elif summary["files"] > 0:
        summary["status"] = "partial"
    else:
        summary["status"] = "failed"

    if summary["failed_cells"]:
        log(f"Failed cells ({len(summary['failed_cells'])}):")
        for failure in summary["failed_cells"][:FAILURE_LOG_LIMIT]:
            log(
                f" - {failure['file']}: row {failure['row']}, "
                f"column '{failure['column']}' ({failure['target_lang']}): "
                f"{failure['error']}"
            )
        remaining_failures = len(summary["failed_cells"]) - FAILURE_LOG_LIMIT
        if remaining_failures > 0:
            log(f" - ... {remaining_failures} additional failed cell(s) are in the returned report.")

    log("Processing cancelled." if summary["cancelled"] else "All processing completed.")
    log(f"Status: {summary['status'].upper()}; Files committed: {summary['files']}, "
        f"Successful: {summary['successful_files']}, Partial: {summary['partial_files']}, "
        f"Failed: {summary['failed_files']}, Total rows: {summary['rows']}, "
        f"Translated cells: {summary['translated_cells']}, Errors: {summary['errors']}")
    if not overwrite_existing:
        log(f"Preserved existing cells count: {summary['skipped_existing']}")
    return summary
