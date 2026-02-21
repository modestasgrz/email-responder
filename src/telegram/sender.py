import httpx
from loguru import logger

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_LENGTH = 4096


def _split_message(text: str, max_length: int = _MAX_LENGTH) -> list[str]:
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Prefer paragraph boundary, then newline, then space
        split_at = text.rfind("\n\n", 0, max_length)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = text.rfind(" ", 0, max_length)
        if split_at == -1:
            split_at = max_length

        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()

    return chunks


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        # Strip whitespaces for possible ValueError(s)
        self._chat_id = chat_id.strip()
        self._url = _TELEGRAM_API.format(token=bot_token.strip())

    def send(self, text: str) -> None:
        chunks = _split_message(text)
        for i, chunk in enumerate(chunks):
            self._post(chunk)
            logger.debug(f"Sent Telegram chunk {i + 1}/{len(chunks)}")
        logger.info(f"Sent digest to Telegram ({len(chunks)} message(s))")

    def _post(self, text: str) -> None:
        with httpx.Client() as client:
            response = client.post(
                self._url,
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if not response.is_success:
                logger.error(
                    f"Telegram API error {response.status_code}: {response.text}"
                )
            response.raise_for_status()
