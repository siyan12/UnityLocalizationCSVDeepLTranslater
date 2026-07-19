"""Application-owned paths and credential storage.

Secrets are stored by the operating system credential backend through keyring.
Non-secret working files live in an explicit per-user data directory so behavior
does not depend on the process working directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

try:
    import keyring
    from keyring.errors import KeyringError
except ImportError:  # Keep imports useful for diagnostics without hiding the issue.
    keyring = None

    class KeyringError(Exception):
        """Fallback error type used when keyring is unavailable."""


APP_DIR_NAME = "UnityLocalizationCSVDeepLTranslater"
KEYRING_SERVICE = APP_DIR_NAME
KEYRING_USERNAME = "DeepL API Key"


class CredentialStoreError(RuntimeError):
    """A safe, user-facing credential storage error."""


def get_app_data_dir() -> Path:
    """Return the explicit, per-user directory used for application data."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME")
        root = Path(base) if base else Path.home() / ".local" / "share"
    return root / APP_DIR_NAME


def get_input_dir() -> Path:
    return get_app_data_dir() / "input"


def get_output_dir() -> Path:
    return get_app_data_dir() / "output"


def verify_credential_store() -> None:
    """Fail safely when keyring has no usable system credential backend."""
    if keyring is None:
        raise CredentialStoreError("The 'keyring' package is not installed.")
    try:
        backend = keyring.get_keyring()
        if float(getattr(backend, "priority", 0)) <= 0:
            raise CredentialStoreError(
                "No usable operating system credential store was found."
            )
    except CredentialStoreError:
        raise
    except Exception as exc:
        raise CredentialStoreError(
            "The operating system credential store is unavailable."
        ) from exc


def load_api_key() -> Optional[str]:
    """Load the DeepL API key without exposing backend exception details."""
    verify_credential_store()
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except KeyringError as exc:
        raise CredentialStoreError(
            "The operating system credential store is unavailable."
        ) from exc


def save_api_key(api_key: str) -> None:
    """Save the DeepL API key in the operating system credential store."""
    verify_credential_store()
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
    except KeyringError as exc:
        raise CredentialStoreError(
            "The operating system credential store is unavailable."
        ) from exc
