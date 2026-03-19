from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError, ServerError

from src.classifier.classifier import EmailClassifier
from src.classifier.models import ClassificationResult, EmailCategory, EmailPriority
from src.gmail.models import Email


def _make_email() -> Email:
    return Email(
        message_id="msg1",
        thread_id="thread1",
        sender="user@example.com",
        subject="Help",
        body="Please help.",
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _server_error() -> ServerError:
    return ServerError(503, {"error": {"code": 503, "message": "Overloaded", "status": "UNAVAILABLE"}})


def _client_error(code: int) -> ClientError:
    return ClientError(code, {"error": {"code": code, "message": "Rate limited", "status": "RESOURCE_EXHAUSTED"}})


def _success_response() -> MagicMock:
    result = ClassificationResult(
        category=EmailCategory.SUPPORT,
        priority=EmailPriority.MEDIUM,
        summary="Needs help",
        needs_reply=True,
        reasoning="Support request",
    )
    return MagicMock(text=result.model_dump_json())


@patch("time.sleep")  # skip actual wait between retries
@patch("src.classifier.classifier.genai.Client")
def test_classify_retries_on_server_error(
    mock_client_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _server_error(),
        _server_error(),
        _success_response(),
    ]

    classifier = EmailClassifier(api_key="fake", model="gemini-flash")
    result = classifier.classify(_make_email())

    assert mock_client.models.generate_content.call_count == 3
    assert result.category == EmailCategory.SUPPORT


@patch("time.sleep")
@patch("src.classifier.classifier.genai.Client")
def test_classify_raises_after_max_attempts(
    mock_client_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = _server_error()

    classifier = EmailClassifier(api_key="fake", model="gemini-flash")

    with pytest.raises(ServerError):
        classifier.classify(_make_email())

    assert mock_client.models.generate_content.call_count == 4  # stop_after_attempt(4)


@patch("time.sleep")
@patch("src.classifier.classifier.genai.Client")
def test_classify_retries_on_429(mock_client_cls: MagicMock, mock_sleep: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _client_error(429),
        _client_error(429),
        _success_response(),
    ]

    classifier = EmailClassifier(api_key="fake", model="gemini-flash")
    result = classifier.classify(_make_email())

    assert mock_client.models.generate_content.call_count == 3
    assert result.category == EmailCategory.SUPPORT


@patch("time.sleep")
@patch("src.classifier.classifier.genai.Client")
def test_classify_retries_on_499(mock_client_cls: MagicMock, mock_sleep: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _client_error(499),
        _success_response(),
    ]

    classifier = EmailClassifier(api_key="fake", model="gemini-flash")
    result = classifier.classify(_make_email())

    assert mock_client.models.generate_content.call_count == 2
    assert result.category == EmailCategory.SUPPORT


@patch("src.classifier.classifier.genai.Client")
def test_classify_does_not_retry_on_non_server_error(
    mock_client_cls: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = ValueError("bad schema")

    classifier = EmailClassifier(api_key="fake", model="gemini-flash")

    with pytest.raises(ValueError):
        classifier.classify(_make_email())

    assert mock_client.models.generate_content.call_count == 1  # no retry
