import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.gmail.client import GmailClient
from src.gmail.models import Email


def _encoded(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _make_email(**kwargs: object) -> Email:
    defaults: dict[str, object] = {
        "message_id": "msg1",
        "thread_id": "thread1",
        "sender": "from@example.com",
        "subject": "Test",
        "body": "Hello",
        "received_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return Email(**defaults)  # type: ignore[arg-type]


def _make_raw_message(
    message_id: str = "msg1",
    thread_id: str = "thread1",
    sender: str = "from@example.com",
    subject: str = "Test",
    body: str = "Hello world",
    internal_date: str = "1705312800000",
) -> dict[str, object]:
    encoded_body = base64.urlsafe_b64encode(body.encode()).decode()
    return {
        "id": message_id,
        "threadId": thread_id,
        "internalDate": internal_date,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
            ],
            "body": {"data": encoded_body},
        },
    }


def _make_client(mock_service: MagicMock) -> GmailClient:
    with (
        patch("src.gmail.client.Path") as mock_path_cls,
        patch("src.gmail.client.Credentials") as mock_creds_cls,
        patch("src.gmail.client.build", return_value=mock_service),
    ):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path_cls.return_value = mock_path

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        return GmailClient("credentials.json", "token.json")


def test_fetch_unread_returns_emails() -> None:
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg1"}]
    }
    mock_service.users().messages().get().execute.return_value = _make_raw_message(
        message_id="msg1"
    )

    client = _make_client(mock_service)
    emails = client.fetch_unread()

    assert len(emails) == 1
    assert emails[0].message_id == "msg1"
    assert emails[0].sender == "from@example.com"
    assert emails[0].subject == "Test"


def test_fetch_unread_empty_inbox() -> None:
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}

    client = _make_client(mock_service)
    emails = client.fetch_unread()

    assert emails == []


def test_fetch_unread_skips_failed_message() -> None:
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg1"}, {"id": "msg2"}]
    }

    def get_side_effect(**kwargs: object) -> MagicMock:
        mock = MagicMock()
        if kwargs.get("id") == "msg1":
            mock.execute.side_effect = RuntimeError("API error")
        else:
            mock.execute.return_value = _make_raw_message(message_id="msg2")
        return mock

    mock_service.users().messages().get.side_effect = get_side_effect

    client = _make_client(mock_service)
    emails = client.fetch_unread()

    assert len(emails) == 1
    assert emails[0].message_id == "msg2"


def test_mark_read_removes_unread_label() -> None:
    mock_service = MagicMock()

    client = _make_client(mock_service)
    client.mark_read("msg1")

    mock_service.users().messages().modify.assert_called_with(
        userId="me",
        id="msg1",
        body={"removeLabelIds": ["UNREAD"]},
    )


def test_add_label_uses_existing_label() -> None:
    mock_service = MagicMock()
    mock_service.users().labels().list().execute.return_value = {
        "labels": [{"id": "Label_1", "name": "AI/Support"}]
    }
    mock_service.users().messages().modify().execute.return_value = {}

    client = _make_client(mock_service)
    client.add_label("msg1", "AI/Support")

    mock_service.users().labels().create.assert_not_called()
    mock_service.users().messages().modify.assert_called_with(
        userId="me",
        id="msg1",
        body={"addLabelIds": ["Label_1"]},
    )


def test_add_label_creates_label_if_missing() -> None:
    mock_service = MagicMock()
    mock_service.users().labels().list().execute.return_value = {"labels": []}
    mock_service.users().labels().create().execute.return_value = {
        "id": "Label_new",
        "name": "AI/Support",
    }
    mock_service.users().messages().modify().execute.return_value = {}

    client = _make_client(mock_service)
    client.add_label("msg1", "AI/Support")

    mock_service.users().labels().create.assert_called()


def test_add_label_caches_label_id() -> None:
    mock_service = MagicMock()
    mock_service.users().labels().list.return_value.execute.return_value = {
        "labels": [{"id": "Label_1", "name": "AI/Spam"}]
    }
    mock_service.users().messages().modify().execute.return_value = {}

    client = _make_client(mock_service)
    client.add_label("msg1", "AI/Spam")
    client.add_label("msg2", "AI/Spam")

    # labels.list should only be called once (second call hits cache)
    assert mock_service.users().labels().list.call_count == 1


# --- _extract_body tests ---


def test_extract_body_multipart_alternative_prefers_plain() -> None:
    client = _make_client(MagicMock())
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _encoded("Plain text content")}},
            {"mimeType": "text/html", "body": {"data": _encoded("<p>HTML content</p>")}},
        ],
    }
    assert client._extract_body(payload) == "Plain text content"


def test_extract_body_multipart_alternative_html_fallback() -> None:
    client = _make_client(MagicMock())
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _encoded("<p>Newsletter content</p>")}},
        ],
    }
    result = client._extract_body(payload)
    assert "Newsletter content" in result
    assert "<p>" not in result


def test_extract_body_multipart_mixed_collects_all_parts() -> None:
    client = _make_client(MagicMock())
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _encoded("Section one")}},
            {"mimeType": "text/plain", "body": {"data": _encoded("Section two")}},
        ],
    }
    result = client._extract_body(payload)
    assert "Section one" in result
    assert "Section two" in result


def test_extract_body_nested_multipart() -> None:
    client = _make_client(MagicMock())
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _encoded("Plain section")}},
                    {"mimeType": "text/html", "body": {"data": _encoded("<p>HTML section</p>")}},
                ],
            },
            {"mimeType": "text/plain", "body": {"data": _encoded("Attachment text")}},
        ],
    }
    result = client._extract_body(payload)
    assert "Plain section" in result
    assert "Attachment text" in result
    assert "<p>" not in result


def test_extract_body_html_only_flat() -> None:
    client = _make_client(MagicMock())
    payload = {
        "mimeType": "text/html",
        "body": {"data": _encoded("<h1>Title</h1><p>Body text</p>")},
    }
    result = client._extract_body(payload)
    assert "Title" in result
    assert "Body text" in result
    assert "<h1>" not in result


def test_extract_body_ignores_image_parts() -> None:
    client = _make_client(MagicMock())
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _encoded("Some text")}},
            {"mimeType": "image/jpeg", "body": {"data": "base64imagedata=="}},
        ],
    }
    assert client._extract_body(payload) == "Some text"


# --- GmailClient.create_draft delegation test ---


def test_client_create_draft_delegates_to_draft_creator() -> None:
    mock_service = MagicMock()
    mock_service.users().drafts().create.return_value.execute.return_value = {"id": "draft_xyz"}

    client = _make_client(mock_service)
    draft_id = client.create_draft(_make_email(), "My reply")

    assert draft_id == "draft_xyz"
    mock_service.users().drafts().create.assert_called_once()


# --- Token refresh path test ---


def test_authenticate_refreshes_expired_credentials() -> None:
    mock_service = MagicMock()
    with (
        patch("src.gmail.client.Path") as mock_path_cls,
        patch("src.gmail.client.Credentials") as mock_creds_cls,
        patch("src.gmail.client.Request") as mock_request_cls,
        patch("src.gmail.client.build", return_value=mock_service),
    ):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path_cls.return_value = mock_path

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_tok"
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        GmailClient("credentials.json", "token.json")

        mock_creds.refresh.assert_called_once_with(mock_request_cls.return_value)
