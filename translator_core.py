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
import time
from collections import Counter
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


class StructureValidationError(ValueError):
    """Protected localization structure is malformed or changed."""


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


def load_csv(path: str) -> Tuple[List[Dict[str, str]], List[str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows: List[Dict[str, str]] = list(reader)
        raw_headers: Optional[Sequence[str]] = reader.fieldnames
        fieldnames: List[str] = list(raw_headers) if raw_headers else []
    return rows, fieldnames


def write_csv(path: str, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def detect_language_columns(fieldnames: List[str], source_col: str) -> Tuple[str, Dict[str, str]]:
    if source_col not in fieldnames:
        raise ValueError(f"Source column '{source_col}' not found in CSV headers.")
    targets: Dict[str, str] = {}
    for h in fieldnames:
        if h in (KEY_COL, ID_COL, source_col):
            continue
        code = LANG_HEADER_TO_DEEPL.get(h)
        if code:
            targets[h] = code
    if not targets:
        raise ValueError("No translatable language columns detected from headers.")
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


def translate_text(
    translator: Any,
    text: str,
    target_lang: str,
    max_retries: int = 5,
    base_delay: float = 0.8,
) -> str:
    last_error = None
    for attempt in range(max_retries):
        try:
            result = translator.translate_text(
                text,
                target_lang=target_lang,
                source_lang="EN",
                preserve_formatting=True,
                split_sentences="nonewlines",
                formality="default",
            )
            return result.text if hasattr(result, "text") else str(result)
        except Exception as e:
            last_error = safe_error_message(e)
            time.sleep(base_delay * (2 ** attempt))
    raise RuntimeError(f"Translation failed after {max_retries} retries: {last_error}")


def should_fill_cell(current_value: Any, preserve_existing: bool) -> bool:
    if not preserve_existing:
        return True
    if current_value is None:
        return True
    if str(current_value).strip() == "":
        return True
    return False


def process_rows(
    rows: List[Dict[str, Any]],
    source_col: str,
    targets_map: Dict[str, str],
    translator: Any,
    preserve_existing: bool = True,
    logger: Optional[Logger] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    cache: Dict[Tuple[str, str], str] = {}
    stats = {
        "rows": len(rows),
        "translated_cells": 0,
        "skipped_existing": 0,
        "skipped_source_invalid": 0,
        "errors": 0,
    }

    new_rows: List[Dict[str, Any]] = []

    for idx, row in enumerate(rows, start=1):
        source_text = row.get(source_col, "")
        if is_skippable_source(source_text):
            stats["skipped_source_invalid"] += 1
            new_rows.append(row)
            continue

        try:
            tokenized, mapping = tokenize_placeholders(source_text)
        except StructureValidationError as error:
            for header in targets_map:
                if should_fill_cell(row.get(header, ""), preserve_existing):
                    stats["errors"] += 1
                    if logger:
                        logger(
                            f"  -> FAILED for '{header}': "
                            f"invalid source structure ({safe_error_message(error)})"
                        )
                else:
                    stats["skipped_existing"] += 1
            new_rows.append(row)
            continue

        for header, target_lang in targets_map.items():
            current_value = row.get(header, "")
            if not should_fill_cell(current_value, preserve_existing):
                stats["skipped_existing"] += 1
                continue

            if logger:
                logger(f"Translating row {idx} to {target_lang}")

            key_cache = (tokenized, target_lang)
            try:
                from_cache = key_cache in cache
                if key_cache in cache:
                    translated = cache[key_cache]
                    if logger:
                        logger("  -> Cache hit")
                else:
                    translated = translate_text(translator, tokenized, target_lang)
                    if logger:
                        logger("  -> API call success")

                detok = detokenize_placeholders(translated, mapping)
                if str(detok).strip() == "":
                    raise StructureValidationError("Translation returned empty text.")
                validate_translated_structure(source_text, detok)
                if not from_cache:
                    cache[key_cache] = translated
                row[header] = detok
                stats["translated_cells"] += 1
                if logger:
                    logger(f"  -> Filled '{header}'")
            except Exception as e:
                stats["errors"] += 1
                if logger:
                    logger(f"  -> FAILED for '{header}': {safe_error_message(e)}")

        new_rows.append(row)

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
    except Exception as e:
        name = e.__class__.__name__
        if name in ("AuthorizationError", "AuthorizationException"):
            return False, "API Key invalid or authentication failed."
        return False, f"Unknown error: {safe_error_message(e, api_key)}"


def run_translation_for_folder(
    api_key: str,
    input_dir: str = "input",
    output_dir: str = "output",
    source_col: str = DEFAULT_SOURCE_COL,
    overwrite_existing: bool = False,
    logger: Optional[Logger] = None,
) -> Dict[str, int]:
    """
    批量翻译 input_dir 下所有 .csv 文件，输出到 output_dir。
    logger: 可选的回调函数，用于输出进度日志。
    返回一个汇总统计：{files, rows, translated_cells, skipped_existing, skipped_source_invalid, errors}
    """
    def log(msg: str) -> None:
        if logger:
            logger(msg)

    ensure_directories(input_dir, output_dir)

    if deepl is None:
        raise RuntimeError("deepl library not installed. Please run: pip install deepl")

    if not api_key:
        raise RuntimeError("Missing DeepL API Key.")

    translator = deepl.Translator(api_key)

    # 收集文件
    all_files = [
        f for f in os.listdir(input_dir)
        if f.lower().endswith(".csv") and os.path.isfile(os.path.join(input_dir, f))
    ]

    summary = {
        "files": 0,
        "rows": 0,
        "translated_cells": 0,
        "skipped_existing": 0,
        "skipped_source_invalid": 0,
        "errors": 0,
    }

    if not all_files:
        log("No CSV files found in input directory. Please add files and try again.")
        return summary

    log(f"Found {len(all_files)} CSV files, starting...")
    for idx, filename in enumerate(all_files, start=1):
        in_path = os.path.join(input_dir, filename)
        out_path = os.path.join(output_dir, filename)

        log(f"[{idx}/{len(all_files)}] Processing file: {filename}")
        try:
            rows, fieldnames = load_csv(in_path)
            source, targets_map = detect_language_columns(fieldnames, source_col)

            new_rows, stats = process_rows(
                rows,
                source,
                targets_map,
                translator,
                preserve_existing=not overwrite_existing,
                logger=log,
            )

            write_csv(out_path, fieldnames, new_rows)

            # Logs & summary
            log(f" - Rows: {stats['rows']}, Translated cells: {stats['translated_cells']}, "
                f"Skipped invalid sources: {stats['skipped_source_invalid']}, Errors: {stats['errors']}"
                + (f", Preserved existing: {stats['skipped_existing']}" if not overwrite_existing else ""))

            summary["files"] += 1
            summary["rows"] += stats["rows"]
            summary["translated_cells"] += stats["translated_cells"]
            summary["skipped_existing"] += stats["skipped_existing"]
            summary["skipped_source_invalid"] += stats["skipped_source_invalid"]
            summary["errors"] += stats["errors"]
        except Exception as e:
            log(f" - Failed to process: {safe_error_message(e, api_key)}")
            summary["errors"] += 1

    log("All processing completed.")
    log(f"Files: {summary['files']}, Total rows: {summary['rows']}, "
        f"Translated cells: {summary['translated_cells']}, Errors: {summary['errors']}")
    if not overwrite_existing:
        log(f"Preserved existing cells count: {summary['skipped_existing']}")
    return summary
