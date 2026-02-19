from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.classifier.models import ClassificationResult, EmailCategory, EmailPriority
from src.drafter.drafter import ReplyDrafter
from src.gmail.models import Email


def _make_email() -> Email:
    return Email(
        message_id="msg1",
        thread_id="thread1",
        sender="user@example.com",
        subject="Need help",
        body="I can't log in.",
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _make_classification(
    category: EmailCategory = EmailCategory.SUPPORT,
) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        priority=EmailPriority.MEDIUM,
        summary="User needs login help",
        needs_reply=True,
        reasoning="Support request",
    )


@patch("src.drafter.drafter.genai.Client")
def test_draft_returns_string(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(
        text="Thank you for reaching out. I can help with your login issue."
    )

    drafter = ReplyDrafter(api_key="fake-key", model="gemini-2.0-flash")
    result = drafter.draft(_make_email(), _make_classification())

    assert isinstance(result, str)
    assert len(result) > 0


@patch("src.drafter.drafter.genai.Client")
def test_draft_strips_whitespace(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(
        text="  \n  Reply content  \n  "
    )

    drafter = ReplyDrafter(api_key="fake-key", model="gemini-2.0-flash")
    result = drafter.draft(_make_email(), _make_classification())

    assert result == "Reply content"


@patch("src.drafter.drafter.genai.Client")
def test_draft_personal_uses_warm_tone(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(text="Reply")

    drafter = ReplyDrafter(api_key="fake-key", model="gemini-2.0-flash")
    drafter.draft(_make_email(), _make_classification(EmailCategory.PERSONAL))

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    system_instruction = call_kwargs["config"].system_instruction.lower()
    assert any(w in system_instruction for w in ["warm", "genuine", "conversational"])


@patch("src.drafter.drafter.genai.Client")
def test_draft_sales_uses_professional_tone(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(text="Reply")

    drafter = ReplyDrafter(api_key="fake-key", model="gemini-2.0-flash")
    drafter.draft(_make_email(), _make_classification(EmailCategory.SALES))

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    system_instruction = call_kwargs["config"].system_instruction.lower()
    assert "professional" in system_instruction


@patch("src.drafter.drafter.genai.Client")
def test_draft_includes_original_email_context(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(text="Reply")

    drafter = ReplyDrafter(api_key="fake-key", model="gemini-2.0-flash")
    drafter.draft(_make_email(), _make_classification())

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]
    assert "user@example.com" in contents
    assert "Need help" in contents
    assert "I can't log in." in contents
