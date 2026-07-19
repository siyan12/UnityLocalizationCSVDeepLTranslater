from types import SimpleNamespace

import pytest

import translator_core
from tests.fakes import FakeDeepLClient
from translator_core import TranslationProviderError, classify_provider_error


class ProviderException(Exception):
    def __init__(self, message, *, status=None, should_retry=False):
        super().__init__(message)
        self.http_status_code = status
        self.should_retry = should_retry


class RequestTimeout(ProviderException):
    pass


class TooManyRequestsException(ProviderException):
    pass


class AuthorizationException(ProviderException):
    pass


class QuotaExceededException(ProviderException):
    pass


@pytest.mark.parametrize(
    ("error", "category", "retryable", "message_fragment"),
    [
        (RequestTimeout("private", should_retry=True), "network", True, "connection"),
        (TooManyRequestsException("private", status=429, should_retry=True), "rate_limit", True, "rate-limited"),
        (AuthorizationException("private", status=403), "authentication", False, "API Key"),
        (QuotaExceededException("private", status=456), "quota", False, "cost-control"),
        (ProviderException("private", status=503, should_retry=True), "service", True, "unavailable"),
        (ProviderException("private", status=400), "invalid_request", False, "parameters"),
        (ValueError("private"), "invalid_request", False, "parameters"),
    ],
)
def test_provider_error_classification(error, category, retryable, message_fragment):
    classification = classify_provider_error(error)

    assert classification.category == category
    assert classification.retryable is retryable
    assert message_fragment in classification.user_message
    assert "private" not in classification.user_message


@pytest.mark.parametrize(
    "error",
    [
        RequestTimeout("failed while translating secret", should_retry=True),
        TooManyRequestsException(
            "failed while translating secret", status=429, should_retry=True
        ),
        ProviderException("failed while translating secret", status=503, should_retry=True),
    ],
)
def test_sdk_terminal_transient_failure_is_not_retried_again_by_app(error):
    client = FakeDeepLClient(
        lambda text, kwargs: (_ for _ in ()).throw(error)
    )

    with pytest.raises(TranslationProviderError) as raised:
        translator_core.translate_text(client, "Secret unreleased ending", "DE")

    assert len(client.calls) == 1
    assert raised.value.category in {"network", "rate_limit", "service"}
    assert "Secret unreleased ending" not in str(raised.value)
    assert "failed while translating secret" not in str(raised.value)


@pytest.mark.parametrize(
    "error",
    [AuthorizationException("private", status=403), QuotaExceededException("private", status=456), ValueError("private")],
)
def test_permanent_provider_error_stops_before_next_target(error):
    client = FakeDeepLClient(
        lambda text, kwargs: (_ for _ in ()).throw(error)
    )

    with pytest.raises(TranslationProviderError):
        translator_core.process_rows(
            [{"English(en)": "Hello", "German(de)": "", "French(fr)": ""}],
            "English(en)",
            {"German(de)": "DE", "French(fr)": "FR"},
            client,
        )

    assert len(client.calls) == 1


@pytest.mark.parametrize(
    ("error", "message_fragment"),
    [
        (AuthorizationException("private credential", status=403), "API Key"),
        (QuotaExceededException("private credential", status=456), "quota"),
        (RequestTimeout("private credential", should_retry=True), "connection"),
    ],
)
def test_api_key_failure_has_safe_actionable_classification(
    monkeypatch, error, message_fragment
):
    class FailingTranslator:
        def __init__(self, api_key):
            pass

        def translate_text(self, text, **kwargs):
            raise error

    monkeypatch.setattr(
        translator_core,
        "deepl",
        SimpleNamespace(Translator=FailingTranslator),
    )

    ok, message = translator_core.test_api_key("not-a-real-key")

    assert not ok
    assert message_fragment in message
    assert "private credential" not in message


def test_terminal_rate_limit_can_be_reported_as_a_partial_cell_failure():
    def respond(text, kwargs):
        if kwargs["target_lang"] == "FR":
            raise TooManyRequestsException("429", status=429, should_retry=True)
        return "Hallo"

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
    assert "rate-limited" in stats["failed_cells"][0]["error"]
    assert len(client.calls) == 2


def test_fatal_provider_error_stops_remaining_files(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    content = "Key,Id,English(en),German(de)\nA,1,Hello,\n"
    (input_dir / "a.csv").write_text(content, encoding="utf-8")
    (input_dir / "b.csv").write_text(content, encoding="utf-8")
    client = FakeDeepLClient(
        lambda text, kwargs: (_ for _ in ()).throw(
            AuthorizationException("secret", status=403)
        )
    )
    monkeypatch.setattr(
        translator_core,
        "deepl",
        SimpleNamespace(Translator=lambda api_key: client),
    )

    summary = translator_core.run_translation_for_folder(
        "not-a-real-key", str(input_dir), str(output_dir)
    )

    assert summary["status"] == "failed"
    assert summary["failed_files"] == 1
    assert summary["provider_error_category"] == "authentication"
    assert "API Key" in summary["fatal_error"]
    assert len(summary["file_results"]) == 1
    assert len(client.calls) == 1
    assert not list(output_dir.glob("*.csv"))
