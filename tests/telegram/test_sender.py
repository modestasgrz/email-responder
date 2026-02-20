from unittest.mock import MagicMock, patch

from src.telegram.sender import TelegramSender, _split_message


def test_split_short_message_is_unchanged() -> None:
    text = "Short message"
    chunks = _split_message(text)
    assert chunks == [text]


def test_split_long_message_into_multiple_chunks() -> None:
    text = "A" * 5000
    chunks = _split_message(text, max_length=4096)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 4096


def test_split_all_chunks_contain_original_content() -> None:
    text = "First part\n\nSecond part\n\nThird part"
    chunks = _split_message(text, max_length=15)
    assert "First part" in chunks
    assert "Second part" in chunks
    assert "Third part" in chunks


def test_split_prefers_paragraph_boundary() -> None:
    text = "Para one.\n\nPara two that is longer."
    # max_length just past the first paragraph
    chunks = _split_message(text, max_length=len("Para one.") + 5)
    assert chunks[0] == "Para one."


def test_split_exact_length_returns_single_chunk() -> None:
    text = "x" * 4096
    chunks = _split_message(text, max_length=4096)
    assert len(chunks) == 1


@patch("src.telegram.sender.httpx.Client")
def test_send_posts_to_correct_url(mock_client_cls: MagicMock) -> None:
    mock_http = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_http
    mock_http.post.return_value = MagicMock(raise_for_status=MagicMock())

    sender = TelegramSender(bot_token="mytoken", chat_id="12345")
    sender.send("Hello from digest")

    mock_http.post.assert_called_once()
    url = mock_http.post.call_args.args[0]
    assert "mytoken" in url
    assert "sendMessage" in url


@patch("src.telegram.sender.httpx.Client")
def test_send_uses_html_parse_mode(mock_client_cls: MagicMock) -> None:
    mock_http = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_http
    mock_http.post.return_value = MagicMock(raise_for_status=MagicMock())

    sender = TelegramSender(bot_token="tok", chat_id="123")
    sender.send("Message")

    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["parse_mode"] == "HTML"
    assert payload["disable_web_page_preview"] is True
    assert payload["chat_id"] == "123"


@patch("src.telegram.sender.httpx.Client")
def test_send_long_message_splits_into_multiple_posts(
    mock_client_cls: MagicMock,
) -> None:
    mock_http = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_http
    mock_http.post.return_value = MagicMock(raise_for_status=MagicMock())

    long_text = "Line\n\n" * 1000  # well over 4096 chars
    sender = TelegramSender(bot_token="tok", chat_id="123")
    sender.send(long_text)

    assert mock_http.post.call_count > 1
