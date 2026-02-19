from loguru import logger
from pydantic import BaseModel

from src.classifier.classifier import EmailClassifier
from src.classifier.models import EmailCategory
from src.digest.collector import NewsletterCollector
from src.digest.summarizer import DigestSummarizer
from src.drafter.drafter import ReplyDrafter
from src.gmail.client import GmailClient
from src.telegram.sender import TelegramSender

_CATEGORY_LABEL: dict[EmailCategory, str] = {
    EmailCategory.SUPPORT: "AI/Support",
    EmailCategory.SALES: "AI/Sales",
    EmailCategory.SPAM: "AI/Spam",
    EmailCategory.NEWSLETTER: "AI/Newsletter",
    EmailCategory.PERSONAL: "AI/Personal",
    EmailCategory.UNKNOWN: "AI/Unknown",
}


class PipelineResult(BaseModel):
    total_emails: int = 0
    drafts_created: int = 0
    newsletters_collected: int = 0
    spam_skipped: int = 0
    unknown_skipped: int = 0
    errors: int = 0
    digest_sent: bool = False


class Pipeline:
    def __init__(
        self,
        gmail_client: GmailClient,
        classifier: EmailClassifier,
        drafter: ReplyDrafter,
        collector: NewsletterCollector,
        summarizer: DigestSummarizer,
        telegram_sender: TelegramSender,
    ) -> None:
        self._gmail = gmail_client
        self._classifier = classifier
        self._drafter = drafter
        self._collector = collector
        self._summarizer = summarizer
        self._telegram = telegram_sender

    def run(self) -> PipelineResult:
        result = PipelineResult()

        emails = self._gmail.fetch_unread()
        result.total_emails = len(emails)

        for email in emails:
            try:
                classification = self._classifier.classify(email)
                label = _CATEGORY_LABEL[classification.category]

                if classification.category == EmailCategory.SPAM:
                    self._gmail.mark_read(email.message_id)
                    self._gmail.add_label(email.message_id, label)
                    result.spam_skipped += 1
                    logger.info(f"Spam skipped: {email.subject!r}")

                elif classification.category == EmailCategory.NEWSLETTER:
                    self._collector.add(email)
                    self._gmail.mark_read(email.message_id)
                    self._gmail.add_label(email.message_id, label)
                    result.newsletters_collected += 1
                    logger.info(f"Newsletter collected: {email.subject!r}")

                elif classification.category == EmailCategory.UNKNOWN:
                    self._gmail.mark_read(email.message_id)
                    self._gmail.add_label(email.message_id, label)
                    result.unknown_skipped += 1
                    logger.info(f"Unknown email skipped: {email.subject!r}")

                else:  # support, sales, personal
                    if classification.needs_reply:
                        reply_body = self._drafter.draft(email, classification)
                        self._gmail.create_draft(email, reply_body)
                        result.drafts_created += 1
                        logger.info(
                            f"Draft created for {classification.category}: {email.subject!r}"
                        )
                    self._gmail.mark_read(email.message_id)
                    self._gmail.add_label(email.message_id, label)

            except Exception as e:
                result.errors += 1
                logger.error(
                    f"Failed to process email {email.message_id} ({email.subject!r}): {e}"
                )
                # Email stays unread → retried next run

        sections = self._collector.get_sections()
        if sections:
            try:
                digest = self._summarizer.compile(sections)
                if digest:
                    self._telegram.send(digest)
                    result.digest_sent = True
            except Exception as e:
                logger.error(f"Failed to send digest: {e}")

        logger.info(
            f"Pipeline complete: {result.total_emails} emails, "
            f"{result.drafts_created} drafts, "
            f"{result.newsletters_collected} newsletters, "
            f"{result.spam_skipped} spam, "
            f"{result.unknown_skipped} unknown, "
            f"{result.errors} errors"
        )
        return result
