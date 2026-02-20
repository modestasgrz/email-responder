import base64
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from loguru import logger

from src.gmail.drafts import DraftCreator
from src.gmail.models import Email

_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks).strip()


def _strip_html(html_text: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html_text)
    return stripper.get_text()


def _decode_part(part: dict[str, Any]) -> str:
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


class GmailClient:
    def __init__(self, credentials_path: str, token_path: str) -> None:
        self._credentials_path = credentials_path
        self._token_path = token_path
        self._service: Any = self._authenticate()
        self._draft_creator = DraftCreator(self._service)
        self._label_cache: dict[str, str] = {}

    def _authenticate(self) -> Any:
        creds: Any = None
        token_path = Path(self._token_path)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)  # type: ignore[no-untyped-call]

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._credentials_path, _SCOPES
                )
                creds = flow.run_local_server(port=0)
            try:
                token_path.write_text(creds.to_json())
            except OSError:
                logger.debug(
                    "Token path is read-only, skipping write-back (normal in Cloud Run)"
                )

        return build("gmail", "v1", credentials=creds)

    def fetch_unread(self) -> list[Email]:
        result = (
            self._service.users().messages().list(userId="me", q="is:unread").execute()
        )
        message_refs: list[dict[str, str]] = result.get("messages", [])

        emails: list[Email] = []
        for ref in message_refs:
            try:
                emails.append(self._fetch_message(ref["id"]))
            except Exception as e:
                logger.error(f"Failed to fetch email {ref['id']}: {e}")

        logger.info(f"Fetched {len(emails)} unread emails")
        return emails

    def _fetch_message(self, message_id: str) -> Email:
        msg = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body = self._extract_body(msg["payload"])
        received_at = datetime.fromtimestamp(
            int(msg["internalDate"]) / 1000, tz=timezone.utc
        )
        return Email(
            message_id=message_id,
            thread_id=msg["threadId"],
            sender=headers.get("From", ""),
            subject=headers.get("Subject", "(no subject)"),
            body=body,
            received_at=received_at,
        )

    def _extract_body(self, payload: dict[str, Any]) -> str:
        mime = payload.get("mimeType", "")
        if "parts" in payload:
            if mime == "multipart/alternative":
                # same content in two formats — prefer plain, fallback to html
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        text = _decode_part(part)
                        if text:
                            return text
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/html":
                        text = _decode_part(part)
                        if text:
                            return _strip_html(text)
                return ""
            else:
                # multipart/mixed, multipart/related, etc — collect ALL parts
                return "\n\n".join(
                    t for part in payload["parts"] if (t := self._extract_body(part))
                )
        else:
            if mime == "text/plain":
                return _decode_part(payload)
            if mime == "text/html":
                text = _decode_part(payload)
                return _strip_html(text) if text else ""
            return ""

    def mark_read(self, message_id: str) -> None:
        self._service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()

    def add_label(self, message_id: str, label_name: str) -> None:
        label_id = self._get_or_create_label(label_name)
        self._service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()

    def create_draft(self, email: Email, reply_body: str) -> str:
        return self._draft_creator.create_draft(email, reply_body)

    def _get_or_create_label(self, label_name: str) -> str:
        if label_name in self._label_cache:
            return self._label_cache[label_name]

        result = self._service.users().labels().list(userId="me").execute()
        for label in result.get("labels", []):
            if label["name"] == label_name:
                self._label_cache[label_name] = label["id"]
                return label["id"]  # type: ignore[no-any-return]

        new_label = (
            self._service.users()
            .labels()
            .create(userId="me", body={"name": label_name})
            .execute()
        )
        label_id: str = new_label["id"]
        self._label_cache[label_name] = label_id
        logger.info(f"Created Gmail label: {label_name}")
        return label_id
