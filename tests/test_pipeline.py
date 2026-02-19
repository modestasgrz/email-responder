from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.classifier.models import ClassificationResult, EmailCategory, EmailPriority
from src.digest.collector import NewsletterCollector
from src.digest.models import NewsletterCategory
from src.digest.summarizer import DigestSummarizer
from src.drafter.drafter import ReplyDrafter
from src.gmail.client import GmailClient
from src.gmail.models import Email
from src.pipeline import Pipeline
from src.telegram.sender import TelegramSender


def _make_email(message_id: str = "msg1", subject: str = "Test") -> Email:
    return Email(
        message_id=message_id,
        thread_id=f"thread_{message_id}",
        sender="user@example.com",
        subject=subject,
        body="Email body",
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _make_classification(
    category: EmailCategory = EmailCategory.SUPPORT,
    needs_reply: bool = True,
) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        priority=EmailPriority.MEDIUM,
        summary="Summary",
        needs_reply=needs_reply,
        reasoning="Reason",
    )


def _make_pipeline(
    emails: list[Email] | None = None,
    classifications: list[ClassificationResult] | None = None,
) -> tuple[
    Pipeline,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    gmail = MagicMock(spec=GmailClient)
    classifier = MagicMock()
    drafter = MagicMock(spec=ReplyDrafter)
    collector = MagicMock(spec=NewsletterCollector)
    summarizer = MagicMock(spec=DigestSummarizer)
    telegram = MagicMock(spec=TelegramSender)

    gmail.fetch_unread.return_value = emails or []
    collector.get_sections.return_value = []  # no newsletters by default

    if classifications:
        classifier.classify.side_effect = classifications

    pipeline = Pipeline(
        gmail_client=gmail,
        classifier=classifier,
        drafter=drafter,
        collector=collector,
        summarizer=summarizer,
        telegram_sender=telegram,
    )
    return pipeline, gmail, classifier, drafter, collector, summarizer, telegram


def test_pipeline_processes_support_email() -> None:
    email = _make_email()
    classification = _make_classification(EmailCategory.SUPPORT, needs_reply=True)

    pipeline, gmail, _, drafter, _, _, _ = _make_pipeline(
        emails=[email], classifications=[classification]
    )
    drafter.draft.return_value = "Here's how I can help you."
    gmail.create_draft.return_value = "draft_1"

    result = pipeline.run()

    assert result.total_emails == 1
    assert result.drafts_created == 1
    gmail.mark_read.assert_called_once_with(email.message_id)
    gmail.add_label.assert_called_once_with(email.message_id, "AI/Support")


def test_pipeline_skips_draft_for_no_reply() -> None:
    email = _make_email()
    classification = _make_classification(EmailCategory.PERSONAL, needs_reply=False)

    pipeline, gmail, _, drafter, _, _, _ = _make_pipeline(
        emails=[email], classifications=[classification]
    )

    result = pipeline.run()

    assert result.drafts_created == 0
    drafter.draft.assert_not_called()
    gmail.mark_read.assert_called_once_with(email.message_id)
    gmail.add_label.assert_called_once_with(email.message_id, "AI/Personal")


def test_pipeline_skips_spam() -> None:
    email = _make_email()
    classification = _make_classification(EmailCategory.SPAM, needs_reply=False)

    pipeline, gmail, _, drafter, _, _, _ = _make_pipeline(
        emails=[email], classifications=[classification]
    )

    result = pipeline.run()

    assert result.spam_skipped == 1
    assert result.drafts_created == 0
    drafter.draft.assert_not_called()
    gmail.mark_read.assert_called_once_with(email.message_id)
    gmail.add_label.assert_called_once_with(email.message_id, "AI/Spam")


def test_pipeline_skips_unknown() -> None:
    email = _make_email(subject="Your order has been shipped")
    classification = _make_classification(EmailCategory.UNKNOWN, needs_reply=False)

    pipeline, gmail, _, drafter, _, _, _ = _make_pipeline(
        emails=[email], classifications=[classification]
    )

    result = pipeline.run()

    assert result.unknown_skipped == 1
    assert result.drafts_created == 0
    drafter.draft.assert_not_called()
    gmail.mark_read.assert_called_once_with(email.message_id)
    gmail.add_label.assert_called_once_with(email.message_id, "AI/Unknown")


def test_pipeline_collects_newsletter_and_sends_digest() -> None:
    email = _make_email(subject="Tech Weekly")
    classification = _make_classification(EmailCategory.NEWSLETTER, needs_reply=False)

    pipeline, gmail, _, drafter, collector, summarizer, telegram = _make_pipeline(
        emails=[email], classifications=[classification]
    )
    collector.get_sections.return_value = [(NewsletterCategory.TECH_BUSINESS, [email])]
    summarizer.compile.return_value = "<b>Digest</b>"

    result = pipeline.run()

    assert result.newsletters_collected == 1
    assert result.digest_sent is True
    collector.add.assert_called_once_with(email)
    drafter.draft.assert_not_called()
    telegram.send.assert_called_once_with("<b>Digest</b>")


def test_pipeline_skips_digest_when_no_newsletters() -> None:
    pipeline, _, _, _, _, summarizer, telegram = _make_pipeline(emails=[])

    result = pipeline.run()

    assert result.digest_sent is False
    summarizer.compile.assert_not_called()
    telegram.send.assert_not_called()


def test_pipeline_continues_on_single_email_failure() -> None:
    emails = [_make_email("msg1"), _make_email("msg2")]

    pipeline, gmail, classifier, _, _, _, _ = _make_pipeline(emails=emails)

    def classify_side_effect(email: Email) -> ClassificationResult:
        if email.message_id == "msg1":
            raise RuntimeError("Gemini error")
        return _make_classification(EmailCategory.SPAM, needs_reply=False)

    classifier.classify.side_effect = classify_side_effect

    result = pipeline.run()

    assert result.errors == 1
    assert result.spam_skipped == 1
    assert result.total_emails == 2


def test_pipeline_handles_telegram_failure_without_crashing() -> None:
    email = _make_email(subject="Newsletter")
    classification = _make_classification(EmailCategory.NEWSLETTER, needs_reply=False)

    pipeline, _, _, _, collector, summarizer, telegram = _make_pipeline(
        emails=[email], classifications=[classification]
    )
    collector.get_sections.return_value = [(NewsletterCategory.TECH_BUSINESS, [email])]
    summarizer.compile.return_value = "Digest content"
    telegram.send.side_effect = RuntimeError("Telegram down")

    result = pipeline.run()

    assert result.digest_sent is False
    assert result.errors == 0


def test_pipeline_processes_multiple_emails() -> None:
    emails = [
        _make_email("msg1", "Support request"),
        _make_email("msg2", "Sales pitch"),
        _make_email("msg3", "Spam"),
        _make_email("msg4", "Newsletter"),
        _make_email("msg5", "Your invoice #1234"),
    ]
    classifications = [
        _make_classification(EmailCategory.SUPPORT, needs_reply=True),
        _make_classification(EmailCategory.SALES, needs_reply=True),
        _make_classification(EmailCategory.SPAM, needs_reply=False),
        _make_classification(EmailCategory.NEWSLETTER, needs_reply=False),
        _make_classification(EmailCategory.UNKNOWN, needs_reply=False),
    ]

    pipeline, gmail, _, drafter, collector, summarizer, telegram = _make_pipeline(
        emails=emails, classifications=classifications
    )
    drafter.draft.return_value = "Reply"
    gmail.create_draft.return_value = "draft_id"
    collector.get_sections.return_value = [
        (NewsletterCategory.TECH_BUSINESS, [emails[3]])
    ]
    summarizer.compile.return_value = "Digest"

    result = pipeline.run()

    assert result.total_emails == 5
    assert result.drafts_created == 2
    assert result.spam_skipped == 1
    assert result.newsletters_collected == 1
    assert result.unknown_skipped == 1
    assert result.digest_sent is True
    assert result.errors == 0
