from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel

from src.digest.models import NewsletterCategory
from src.gmail.models import Email

_CATEGORIZE_PROMPT = """Classify this newsletter email into exactly one category:

- tech_business: technology, programming, AI/ML, startups, business, finance, science, software
- music: music releases, artists, concerts, music industry, streaming services, bands, record labels
- other: sports, lifestyle, gaming, travel, food, art, politics, or anything not clearly tech or music"""


class _NewsletterCategoryResult(BaseModel):
    category: NewsletterCategory


class NewsletterCollector:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._items: dict[NewsletterCategory, list[Email]] = {
            NewsletterCategory.TECH_BUSINESS: [],
            NewsletterCategory.MUSIC: [],
            NewsletterCategory.OTHER: [],
        }

    def add(self, email: Email) -> None:
        category = self._categorize(email)
        self._items[category].append(email)
        logger.debug(
            f"Collected newsletter {email.message_id} as {category} ({email.subject!r})"
        )

    def _categorize(self, email: Email) -> NewsletterCategory:
        prompt = f"From: {email.sender}\nSubject: {email.subject}\n\n{email.body[:500]}"
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_CATEGORIZE_PROMPT,
                    response_mime_type="application/json",
                    response_schema=_NewsletterCategoryResult,
                ),
            )
            assert response.text is not None, "Gemini returned empty response"
            result = _NewsletterCategoryResult.model_validate_json(response.text)
            return result.category
        except Exception as e:
            logger.warning(
                f"Failed to categorize newsletter {email.message_id}: {e}. "
                "Defaulting to other."
            )
            return NewsletterCategory.OTHER

    def get_sections(self) -> list[tuple[NewsletterCategory, list[Email]]]:
        return [(cat, emails) for cat, emails in self._items.items() if emails]

    @property
    def total(self) -> int:
        return sum(len(emails) for emails in self._items.values())
