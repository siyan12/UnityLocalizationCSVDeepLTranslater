import pathlib

import app_version
import gui_app
import pytest
from scripts.verify_release_version import verify_release_version


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_runtime_title_uses_application_version():
    assert app_version.__version__ == "1.3.0"
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


def test_release_tag_must_match_shared_semantic_version():
    assert verify_release_version("v1.3.0") == "1.3.0"
    with pytest.raises(ValueError, match="does not match"):
        verify_release_version("v1.3.1")
