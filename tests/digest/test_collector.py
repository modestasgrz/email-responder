from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.digest.collector import (
    NewsletterCategory,
    NewsletterCollector,
    _NewsletterCategoryResult,
)
from src.gmail.models import Email


def _make_email(
    sender: str = "news@techcrunch.com",
    subject: str = "Weekly Digest",
) -> Email:
    return Email(
        message_id="msg1",
        thread_id="thread1",
        sender=sender,
        subject=subject,
        body="Newsletter content here",
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _mock_categorize_response(category: NewsletterCategory) -> MagicMock:
    return MagicMock(
        text=_NewsletterCategoryResult(category=category).model_dump_json()
    )


@patch("src.digest.collector.genai.Client")
def test_add_routes_to_tech_business(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_categorize_response(
        NewsletterCategory.TECH_BUSINESS
    )

    collector = NewsletterCollector(api_key="fake", model="fake-model")
    collector.add(_make_email())

    sections = collector.get_sections()
    cats = [cat for cat, _ in sections]
    assert NewsletterCategory.TECH_BUSINESS in cats


@patch("src.digest.collector.genai.Client")
def test_add_routes_to_music(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_categorize_response(
        NewsletterCategory.MUSIC
    )

    collector = NewsletterCollector(api_key="fake", model="fake-model")
    collector.add(_make_email(sender="noreply@soundcloud.com"))

    sections = collector.get_sections()
    cats = [cat for cat, _ in sections]
    assert NewsletterCategory.MUSIC in cats


@patch("src.digest.collector.genai.Client")
def test_add_routes_to_other(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_categorize_response(
        NewsletterCategory.OTHER
    )

    collector = NewsletterCollector(api_key="fake", model="fake-model")
    collector.add(_make_email(subject="Weekend sports roundup"))

    sections = collector.get_sections()
    cats = [cat for cat, _ in sections]
    assert NewsletterCategory.OTHER in cats


@patch("src.digest.collector.genai.Client")
def test_categorize_failure_defaults_to_other(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = RuntimeError("API error")

    collector = NewsletterCollector(api_key="fake", model="fake-model")
    collector.add(_make_email())

    sections = collector.get_sections()
    cats = [cat for cat, _ in sections]
    assert NewsletterCategory.OTHER in cats


@patch("src.digest.collector.genai.Client")
def test_get_sections_excludes_empty_categories(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_categorize_response(
        NewsletterCategory.TECH_BUSINESS
    )

    collector = NewsletterCollector(api_key="fake", model="fake-model")
    collector.add(_make_email())

    sections = collector.get_sections()
    # Only TECH_BUSINESS has an item — MUSIC and OTHER should be absent
    assert len(sections) == 1
    assert sections[0][0] == NewsletterCategory.TECH_BUSINESS


@patch("src.digest.collector.genai.Client")
def test_total_counts_all_items(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _mock_categorize_response(NewsletterCategory.TECH_BUSINESS),
        _mock_categorize_response(NewsletterCategory.MUSIC),
    ]

    collector = NewsletterCollector(api_key="fake", model="fake-model")
    collector.add(_make_email())
    collector.add(_make_email(sender="bandcamp@mail.com"))

    assert collector.total == 2


@patch("src.digest.collector.genai.Client")
def test_empty_collector_returns_no_sections(mock_client_cls: MagicMock) -> None:
    mock_client_cls.return_value = MagicMock()

    collector = NewsletterCollector(api_key="fake", model="fake-model")
    assert collector.get_sections() == []
    assert collector.total == 0
