from types import SimpleNamespace

import pytest

import translator_core
from tests.fakes import FakeDeepLClient


class RequestTimeout(Exception):
    pass


class TooManyRequestsException(Exception):
    pass


class AuthorizationException(Exception):
    pass


class QuotaExceededException(Exception):
    pass


@pytest.mark.parametrize(
    "error_type",
    [RequestTimeout, TooManyRequestsException, AuthorizationException, QuotaExceededException],
)
def test_provider_failures_are_reported_by_safe_type_without_cell_text(
    monkeypatch, error_type
):
    sensitive_source = "Secret unreleased ending"
    client = FakeDeepLClient(
        lambda text, kwargs: (_ for _ in ()).throw(
            error_type(f"failed while translating {sensitive_source}")
        )
    )
    monkeypatch.setattr(translator_core.time, "sleep", lambda seconds: None)

    result, stats = translator_core.process_rows(
        [{"English(en)": sensitive_source, "German(de)": "Existing"}],
        "English(en)",
        {"German(de)": "DE"},
        client,
        preserve_existing=False,
    )

    assert result[0]["German(de)"] == "Existing"
    assert stats["translated_cells"] == 0
    assert stats["errors"] == 1
    assert len(client.calls) == 5
    report = repr(stats["failed_cells"])
    assert error_type.__name__ in report
    assert sensitive_source not in report


def test_api_key_authentication_failure_has_actionable_classification(monkeypatch):
    class FailingTranslator:
        def __init__(self, api_key):
            pass

        def translate_text(self, text, **kwargs):
            raise AuthorizationException("provider echoed a credential")

    monkeypatch.setattr(
        translator_core,
        "deepl",
        SimpleNamespace(Translator=FailingTranslator),
    )

    ok, message = translator_core.test_api_key("not-a-real-key")

    assert not ok
    assert message == "API Key invalid or authentication failed."


def test_partial_failure_statistics_keep_successful_cells(monkeypatch):
    def respond(text, kwargs):
        if kwargs["target_lang"] == "FR":
            raise TooManyRequestsException("429")
        return "Hallo"

    monkeypatch.setattr(translator_core.time, "sleep", lambda seconds: None)
    client = FakeDeepLClient(respond)

    result, stats = translator_core.process_rows(
        [{"English(en)": "Hello", "German(de)": "", "French(fr)": "Ancien"}],
        "English(en)",
        {"German(de)": "DE", "French(fr)": "FR"},
        client,
        preserve_existing=False,
    )

    assert result[0]["German(de)"] == "Hallo"
    assert result[0]["French(fr)"] == "Ancien"
    assert stats["translated_cells"] == 1
    assert stats["errors"] == 1
    assert stats["failed_cells"][0]["target_lang"] == "FR"
