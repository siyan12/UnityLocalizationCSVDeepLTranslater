import pathlib

import app_version
import gui_app
import pytest
from scripts.verify_release_version import is_valid_semver, verify_release_version


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_runtime_title_uses_application_version():
    assert gui_app.APP_TITLE.endswith(f"v{app_version.__version__}")


def test_project_metadata_reads_version_from_shared_attribute():
    metadata = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'dynamic = ["version"]' in metadata
    assert 'version = {attr = "app_version.__version__"}' in metadata
    assert '"app_version"' in metadata
    assert '"pyinstaller>=6.10,<7"' in metadata


def test_pyinstaller_spec_uses_shared_version_and_windowed_onefile_mode():
    spec = (PROJECT_ROOT / "CSVTranslator.spec").read_text(encoding="utf-8")

    assert "from app_version import __version__" in spec
    assert "name=f'CSVTranslator-{__version__}'" in spec
    assert "console=False" in spec
    assert "COLLECT(" not in spec


def test_release_workflow_uses_locked_protected_draft_pipeline():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "requirements-release.lock" in workflow
    assert "merge-base --is-ancestor" in workflow
    assert "--check-runtime" in workflow
    assert "environment: release" in workflow
    assert "--draft" in workflow
    assert "publish:" in workflow


def test_release_tag_must_match_shared_semantic_version():
    current_tag = f"v{app_version.__version__}"
    assert verify_release_version(current_tag) == app_version.__version__
    mismatched_tag = "v0.0.1" if app_version.__version__ == "0.0.0" else "v0.0.0"
    with pytest.raises(ValueError, match="does not match"):
        verify_release_version(mismatched_tag)


@pytest.mark.parametrize(
    "tag",
    [
        "1.0.0",
        "v01.0.0",
        "v1.0.0-01",
        "v1.0.0-alpha.01",
        "v1.0",
    ],
)
def test_release_tag_rejects_invalid_semver(tag):
    with pytest.raises(ValueError, match="valid SemVer|start with"):
        verify_release_version(tag)


@pytest.mark.parametrize(
    "version",
    [
        "1.0.0",
        "1.0.0-0",
        "1.0.0-alpha.1",
        "1.0.0+build.01",
    ],
)
def test_semver_validator_accepts_valid_versions(version):
    assert is_valid_semver(version)
