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
from typing import Dict, List, Tuple, Any, Match, Optional, Sequence, Callable

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

PLACEHOLDER_PATTERNS = [
    re.compile(r"\{[^}]*\}"),  # {0}, {name}
    re.compile(r"%[sdif]"),    # %s, %d, %i, %f
    re.compile(r"\$\d+"),      # $1, $2
]

TOKEN_PREFIX = "§§PH_"
TOKEN_SUFFIX = "§§"

Logger = Callable[[str], None]


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
    mapping: Dict[str, str] = {}
    token_index = 0

    def repl(match: Match[str]) -> str:
        nonlocal token_index
        original = match.group(0)
        token = f"{TOKEN_PREFIX}{token_index}{TOKEN_SUFFIX}"
        mapping[token] = original
        token_index += 1
        return token

    tokenized = text
    for pattern in PLACEHOLDER_PATTERNS:
        tokenized = pattern.sub(repl, tokenized)
    return tokenized, mapping


def detokenize_placeholders(text: str, mapping: Dict[str, str]) -> str:
    out = text
    for token, original in mapping.items():
        out = out.replace(token, original)
    return out


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
            last_error = e
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

        tokenized, mapping = tokenize_placeholders(source_text)

        for header, target_lang in targets_map.items():
            current_value = row.get(header, "")
            if not should_fill_cell(current_value, preserve_existing):
                stats["skipped_existing"] += 1
                continue

            if logger:
                snippet = (source_text or "").strip()
                if len(snippet) > 60:
                    snippet = snippet[:60] + "..."
                logger(f"Translating row {idx} to {target_lang}: '{snippet}'")

            key_cache = (tokenized, target_lang)
            try:
                if key_cache in cache:
                    translated = cache[key_cache]
                    if logger:
                        logger("  -> Cache hit")
                else:
                    translated = translate_text(translator, tokenized, target_lang)
                    cache[key_cache] = translated
                    if logger:
                        logger("  -> API call success")

                detok = detokenize_placeholders(translated, mapping)
                if str(detok).strip() != "":
                    row[header] = detok
                    stats["translated_cells"] += 1
                    if logger:
                        out_snippet = detok.strip()
                        if len(out_snippet) > 60:
                            out_snippet = out_snippet[:60] + "..."
                        logger(f"  -> Filled '{header}': '{out_snippet}'")
            except Exception as e:
                stats["errors"] += 1
                if logger:
                    logger(f"  -> FAILED for '{header}': {e}")

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
        return False, f"Unknown error: {e}"


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
            log(f" - Failed to process: {e}")
            summary["errors"] += 1

    log("All processing completed.")
    log(f"Files: {summary['files']}, Total rows: {summary['rows']}, "
        f"Translated cells: {summary['translated_cells']}, Errors: {summary['errors']}")
    if not overwrite_existing:
        log(f"Preserved existing cells count: {summary['skipped_existing']}")
    return summary