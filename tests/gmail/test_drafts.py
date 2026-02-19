import base64
from datetime import datetime, timezone
from email import message_from_bytes
from unittest.mock import MagicMock

from src.gmail.drafts import DraftCreator
from src.gmail.models import Email


def _make_email(**kwargs: object) -> Email:
    defaults: dict[str, object] = {
        "message_id": "msg123",
        "thread_id": "thread123",
        "sender": "sender@example.com",
        "subject": "Test Subject",
        "body": "Hello",
        "received_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return Email(**defaults)  # type: ignore[arg-type]


def test_create_draft_returns_draft_id() -> None:
    mock_service = MagicMock()
    mock_service.users().drafts().create().execute.return_value = {"id": "draft_abc"}

    creator = DraftCreator(mock_service)
    draft_id = creator.create_draft(_make_email(), "Thank you for reaching out.")

    assert draft_id == "draft_abc"


def test_create_draft_includes_thread_id() -> None:
    mock_service = MagicMock()
    mock_service.users().drafts().create().execute.return_value = {"id": "d1"}

    creator = DraftCreator(mock_service)
    creator.create_draft(_make_email(thread_id="thread_xyz"), "Reply body")

    call_kwargs = mock_service.users().drafts().create.call_args.kwargs
    assert call_kwargs["body"]["message"]["threadId"] == "thread_xyz"


def test_create_draft_sets_reply_headers() -> None:
    mock_service = MagicMock()
    mock_service.users().drafts().create().execute.return_value = {"id": "d1"}

    creator = DraftCreator(mock_service)
    creator.create_draft(_make_email(message_id="original_msg_id"), "Reply body")

    call_kwargs = mock_service.users().drafts().create.call_args.kwargs
    raw = call_kwargs["body"]["message"]["raw"]
    msg = message_from_bytes(base64.urlsafe_b64decode(raw))

    assert msg["In-Reply-To"] == "original_msg_id"
    assert msg["References"] == "original_msg_id"


def test_create_draft_sets_recipient() -> None:
    mock_service = MagicMock()
    mock_service.users().drafts().create().execute.return_value = {"id": "d1"}

    creator = DraftCreator(mock_service)
    creator.create_draft(_make_email(sender="alice@example.com"), "Hi Alice")

    call_kwargs = mock_service.users().drafts().create.call_args.kwargs
    raw = call_kwargs["body"]["message"]["raw"]
    msg = message_from_bytes(base64.urlsafe_b64decode(raw))

    assert msg["To"] == "alice@example.com"
