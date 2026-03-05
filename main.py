import sys

from loguru import logger

from src.classifier.classifier import EmailClassifier
from src.config import Settings
from src.digest.collector import NewsletterCollector
from src.digest.summarizer import DigestSummarizer
from src.drafter.drafter import ReplyDrafter
from src.gmail.client import GmailClient
from src.pipeline import Pipeline
from src.telegram.sender import TelegramSender


def main() -> None:
    config = Settings()  # type: ignore[call-arg]  # reads required fields from .env

    logger.remove()
    logger.add(sys.stderr, level=config.log_level)

    logger.info("Starting email responder pipeline")

    gmail_client = GmailClient(
        credentials_path=config.gmail_credentials_path,
        token_path=config.gmail_token_path,
        token_secret_name=config.gmail_token_secret_name,
        gcp_project_id=config.gcp_project_id,
    )
    classifier = EmailClassifier(
        api_key=config.gemini_api_key.get_secret_value(),
        model=config.gemini_model,
    )
    drafter = ReplyDrafter(
        api_key=config.gemini_api_key.get_secret_value(),
        model=config.gemini_model,
    )
    collector = NewsletterCollector(
        api_key=config.gemini_api_key.get_secret_value(),
        model=config.gemini_model,
    )
    summarizer = DigestSummarizer(
        api_key=config.gemini_api_key.get_secret_value(),
        model=config.gemini_model,
    )
    telegram_sender = TelegramSender(
        bot_token=config.telegram_bot_token.get_secret_value(),
        chat_id=config.telegram_chat_id.get_secret_value(),
    )

    pipeline = Pipeline(
        gmail_client=gmail_client,
        classifier=classifier,
        drafter=drafter,
        collector=collector,
        summarizer=summarizer,
        telegram_sender=telegram_sender,
    )

    result = pipeline.run()

    logger.info(
        f"Done: {result.total_emails} emails processed, "
        f"{result.drafts_created} drafts created, "
        f"digest_sent={result.digest_sent}"
    )


if __name__ == "__main__":
    main()
