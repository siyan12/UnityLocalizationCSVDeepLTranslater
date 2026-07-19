"""Fail a release when its tag and packaged version do not match the app version."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def load_version(root: Path = ROOT) -> str:
    """Return the sole literal version without importing application code."""
    version_source = (root / "app_version.py").read_text(encoding="utf-8")
    match = re.search(
        r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$',
        version_source,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError("app_version.py must define a literal __version__ value.")

    with (root / "pyproject.toml").open("rb") as pyproject_file:
        metadata = tomllib.load(pyproject_file)
    if metadata["project"].get("dynamic") != ["version"]:
        raise ValueError("pyproject.toml must declare version as its only dynamic field.")
    dynamic_version = metadata.get("tool", {}).get("setuptools", {}).get(
        "dynamic", {}
    ).get("version")
    if dynamic_version != {"attr": "app_version.__version__"}:
        raise ValueError(
            "pyproject.toml version must reference app_version.__version__."
        )
    return match.group(1)


def verify_release_version(tag: str, root: Path = ROOT) -> str:
    """Validate a v-prefixed SemVer tag against every release version field."""
    if not tag.startswith("v"):
        raise ValueError(f"Release tag must start with 'v'; received {tag!r}.")
    tag_version = tag[1:]
    if SEMVER_PATTERN.fullmatch(tag_version) is None:
        raise ValueError(f"Release tag is not valid SemVer: {tag!r}.")

    app_version = load_version(root)
    if app_version != tag_version:
        raise ValueError(
            f"Tag {tag!r} does not match app_version.py={app_version!r}."
        )
    return tag_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="Git tag, for example v1.3.0")
    args = parser.parse_args(argv)
    try:
        version = verify_release_version(args.tag)
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(f"Release version verification failed: {error}", file=sys.stderr)
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
