from google import genai
from google.genai import types
from loguru import logger

from src.classifier.models import ClassificationResult
from src.config import EMAIL_BODY_MAX_CHARS
from src.gmail.models import Email

_SYSTEM_PROMPT = """You are an email classifier. Classify each email into exactly one of these categories:

- support: Customer/user asking for help, reporting bugs, requesting features, or needing technical assistance
- sales: Vendor pitches, partnership proposals, sponsorship requests, or business development outreach
- spam: Unsolicited mass email, phishing, irrelevant promotions, or automated junk
- newsletter: Subscription-based content digests, blog updates, industry news, or product announcements
- personal: Direct communication from a real person who knows you — colleagues, friends, family, or professional contacts
- unknown: Transactional emails that don't fit the above — invoices, order confirmations, flight/hotel bookings, receipts, review requests, automated notifications etc

For needs_reply:
- True for support, sales, personal (unless clearly automated/no-reply)
- False for spam, newsletter, and unknown
- False for automated notifications even if categorized as personal

Be concise: summary is one sentence, reasoning is one sentence."""


class EmailClassifier:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def classify(self, email: Email) -> ClassificationResult:
        prompt = (
            f"From: {email.sender}\n"
            f"Subject: {email.subject}\n\n"
            f"{email.body[:EMAIL_BODY_MAX_CHARS]}"
        )

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ClassificationResult,
            ),
        )

        assert response.text is not None, "Gemini returned empty response"
        result = ClassificationResult.model_validate_json(response.text)
        logger.debug(
            f"Classified {email.message_id} as {result.category} "
            f"(priority={result.priority}): {result.reasoning}"
        )
        return result
