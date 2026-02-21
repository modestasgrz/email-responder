from google import genai
from google.genai import types
from loguru import logger

from src.digest.collector import NewsletterCategory
from src.gmail.models import Email
from src.utils.retry import gemini_retry

_SECTION_LABELS: dict[NewsletterCategory, str] = {
    NewsletterCategory.TECH_BUSINESS: "Tech & Business",
    NewsletterCategory.MUSIC: "Music",
    NewsletterCategory.OTHER: "Other",
}

_SYSTEM_PROMPT = """You are a newsletter digest compiler. I will give you newsletter emails grouped by category.

For each email, extract the key news items and format them for a Telegram message using HTML.

Output format for each item:
• <b>What:</b> One sentence describing the news/tool/announcement
  <b>Why it matters:</b> One sentence on the problem it solves or impact it has
  <b>Sentiment:</b> One sentence on community feedback (write "N/A" if unknown)
  <b>Source:</b> <a href="URL">Publication Name</a>

Group items under bold section headers: <b>📊 Tech &amp; Business</b>, <b>🎵 Music</b>, <b>📌 Other</b>

Only include sections that have content. Keep it scannable. No fluff."""


def _build_prompt(sections: list[tuple[NewsletterCategory, list[Email]]]) -> str:
    parts: list[str] = []
    for category, emails in sections:
        label = _SECTION_LABELS[category]
        parts.append(f"=== {label} ===")
        for email in emails:
            parts.append(f"\nFrom: {email.sender}")
            parts.append(f"Subject: {email.subject}")
            parts.append(f"Content:\n{email.body[:3000]}")
            parts.append("---")
    return "\n".join(parts)


class DigestSummarizer:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    @gemini_retry
    def compile(self, sections: list[tuple[NewsletterCategory, list[Email]]]) -> str:
        if not sections:
            return ""

        total = sum(len(emails) for _, emails in sections)
        logger.info(f"Compiling digest from {total} newsletter emails")

        response = self._client.models.generate_content(
            model=self._model,
            contents=_build_prompt(sections),
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
            ),
        )

        assert response.text is not None, "Gemini returned empty response"
        digest: str = response.text.strip()
        logger.info(f"Compiled digest ({len(digest)} chars)")
        return digest
