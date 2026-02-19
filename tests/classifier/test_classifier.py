from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.classifier.classifier import EmailClassifier
from src.classifier.models import ClassificationResult, EmailCategory, EmailPriority
from src.gmail.models import Email


def _make_email(body: str = "Please help me with my account.") -> Email:
    return Email(
        message_id="msg1",
        thread_id="thread1",
        sender="user@example.com",
        subject="I need help",
        body=body,
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _make_classification_json(category: EmailCategory = EmailCategory.SUPPORT) -> str:
    return ClassificationResult(
        category=category,
        priority=EmailPriority.HIGH,
        summary="User needs account help",
        needs_reply=True,
        reasoning="Direct support request",
    ).model_dump_json()


@patch("src.classifier.classifier.genai.Client")
def test_classify_returns_classification_result(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(
        text=_make_classification_json()
    )

    classifier = EmailClassifier(api_key="fake-key", model="gemini-3-flash-preview")
    result = classifier.classify(_make_email())

    assert isinstance(result, ClassificationResult)
    assert result.category == EmailCategory.SUPPORT
    assert result.needs_reply is True

    # Verify email content is passed to Gemini
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert "user@example.com" in call_kwargs["contents"]
    assert "I need help" in call_kwargs["contents"]

    # Verify structured output is configured
    config = call_kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is ClassificationResult


@patch("src.classifier.classifier.EMAIL_BODY_MAX_CHARS", 100)
@patch("src.classifier.classifier.genai.Client")
def test_classify_truncates_long_body(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(
        text=_make_classification_json()
    )

    classifier = EmailClassifier(api_key="fake-key", model="gemini-3-flash-preview")
    classifier.classify(_make_email(body="x" * 500))

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    # body truncated to patched limit (100) + small header overhead
    assert len(call_kwargs["contents"]) < 200
