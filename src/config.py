from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Max characters of email body passed to LLM calls.
# 5000 chars ≈ 1250 tokens — enough context for classification/drafting
# without inflating cost. Common engineering practice: 5k–10k chars.
EMAIL_BODY_MAX_CHARS: int = 5000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    gmail_credentials_path: str = "credentials.json"
    gmail_token_path: str = "token.json"
    gemini_api_key: SecretStr
    gemini_model: str = "gemini-3-flash-preview"
    telegram_bot_token: SecretStr
    telegram_chat_id: str
    log_level: str = "INFO"
