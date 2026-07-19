#!/usr/bin/env python3
"""Reject tracked/staged config files and likely credentials without printing them."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import PurePosixPath


RULES = {
    "DeepL key-shaped value": re.compile(rb"(?i)(?<![0-9a-f])[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}:fx(?![\w])"),
    "assigned API credential": re.compile(
        rb"(?i)\b(?:deepl[_-]?)?api[_-]?key\b\s*[:=]\s*['\"]?(?!\s*(?:your|example|test|fake|none|\$|\{|<))[A-Za-z0-9_:+/=-]{20,}"
    ),
}


def git_output(*args: str) -> bytes:
    return subprocess.check_output(("git", *args), stderr=subprocess.DEVNULL)


def candidate_paths(staged: bool) -> list[str]:
    if staged:
        raw = git_output("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:
        # Include new, non-ignored files so a manual run also checks work not yet staged.
        raw = git_output("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return [item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item]


def file_content(path: str, staged: bool) -> bytes:
    if staged:
        return git_output("show", f":{path}")
    with open(path, "rb") as handle:
        return handle.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true", help="scan only the staged snapshot")
    args = parser.parse_args()
    findings: list[tuple[str, str]] = []

    for path in candidate_paths(args.staged):
        normalized = PurePosixPath(path.replace("\\", "/"))
        if normalized.name.lower() == "config.ini":
            findings.append((path, "forbidden config.ini path"))
            continue
        try:
            content = file_content(path, args.staged)
        except (OSError, subprocess.CalledProcessError):
            continue
        if b"\0" in content[:8192]:
            continue
        for rule_name, pattern in RULES.items():
            if pattern.search(content):
                findings.append((path, rule_name))

    if findings:
        print("Credential safety check failed (secret values are intentionally hidden):")
        for path, rule_name in findings:
            print(f"- {path}: {rule_name}")
        return 1
    print("Credential safety check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
