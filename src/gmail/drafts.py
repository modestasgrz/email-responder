import base64
from email.mime.text import MIMEText
from typing import Any

from loguru import logger

from src.gmail.models import Email


class DraftCreator:
    def __init__(self, service: Any) -> None:
        self._service = service

    def create_draft(self, email: Email, reply_body: str) -> str:
        """Create a threaded Gmail draft reply. Returns the draft ID."""
        message = MIMEText(reply_body, "plain")
        message["To"] = email.sender
        message["Subject"] = f"Re: {email.subject}"
        message["In-Reply-To"] = email.message_id
        message["References"] = email.message_id

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        draft = (
            self._service.users()
            .drafts()
            .create(
                userId="me",
                body={
                    "message": {
                        "raw": raw,
                        "threadId": email.thread_id,
                    }
                },
            )
            .execute()
        )

        draft_id: str = draft["id"]
        logger.debug(f"Created draft {draft_id} for thread {email.thread_id}")
        return draft_id
