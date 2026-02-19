from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.digest.models import NewsletterCategory
from src.digest.summarizer import DigestSummarizer
from src.gmail.models import Email


def _make_email(subject: str = "Tech News") -> Email:
    return Email(
        message_id="msg1",
        thread_id="thread1",
        sender="news@example.com",
        subject=subject,
        body="Some tech news content about AI and startups.",
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


@patch("src.digest.summarizer.genai.Client")
def test_compile_returns_string(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(
        text="<b>Tech &amp; Business</b>\n• Some item"
    )

    summarizer = DigestSummarizer(api_key="fake-key", model="gemini-2.0-flash")
    result = summarizer.compile(
        [(NewsletterCategory.TECH_BUSINESS, [_make_email()])]
    )

    assert isinstance(result, str)
    assert len(result) > 0


@patch("src.digest.summarizer.genai.Client")
def test_compile_returns_empty_for_no_sections(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    summarizer = DigestSummarizer(api_key="fake-key", model="gemini-2.0-flash")
    result = summarizer.compile([])

    assert result == ""
    mock_client.models.generate_content.assert_not_called()


@patch("src.digest.summarizer.genai.Client")
def test_compile_strips_whitespace(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(
        text="  \n  Digest content  \n  "
    )

    summarizer = DigestSummarizer(api_key="fake-key", model="gemini-2.0-flash")
    result = summarizer.compile(
        [(NewsletterCategory.TECH_BUSINESS, [_make_email()])]
    )

    assert result == "Digest content"


@patch("src.digest.summarizer.genai.Client")
def test_compile_includes_email_content_in_prompt(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(text="Digest")

    summarizer = DigestSummarizer(api_key="fake-key", model="gemini-2.0-flash")
    summarizer.compile(
        [(NewsletterCategory.TECH_BUSINESS, [_make_email(subject="AI Weekly")])]
    )

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert "AI Weekly" in call_kwargs["contents"]
