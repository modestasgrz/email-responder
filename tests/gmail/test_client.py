import base64
from unittest.mock import MagicMock, patch

from src.gmail.client import GmailClient


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
    mock_service.users().labels().list().execute.return_value = {
        "labels": [{"id": "Label_1", "name": "AI/Spam"}]
    }
    mock_service.users().messages().modify().execute.return_value = {}

    client = _make_client(mock_service)
    client.add_label("msg1", "AI/Spam")
    client.add_label("msg2", "AI/Spam")

    # labels.list should only be called once (second call hits cache)
    assert mock_service.users().labels().list.call_count == 1
