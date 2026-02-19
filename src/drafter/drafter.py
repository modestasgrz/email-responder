from google import genai
from google.genai import types
from loguru import logger

from src.classifier.models import ClassificationResult, EmailCategory
from src.config import EMAIL_BODY_MAX_CHARS
from src.gmail.models import Email

_TONE_BY_CATEGORY: dict[EmailCategory, str] = {
    EmailCategory.SUPPORT: (
        "You are a helpful support representative. "
        "Be solution-oriented, empathetic, and clear. "
        "Provide actionable next steps when possible."
    ),
    EmailCategory.SALES: (
        "You are a professional responding to a sales or business inquiry. "
        "Be polite and professional but non-committal. "
        "Thank them for reaching out without making any promises."
    ),
    EmailCategory.PERSONAL: (
        "You are responding to a personal email from someone you know. "
        "Be warm, genuine, and conversational."
    ),
}

_SYSTEM_BASE = """{tone}

Write only the email body — no subject line, no greeting like "Dear X", no sign-off with your name. Start directly with the message content. Keep it concise."""


class ReplyDrafter:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def draft(self, email: Email, classification: ClassificationResult) -> str:
        tone = _TONE_BY_CATEGORY.get(
            classification.category,
            "Be professional and helpful.",
        )
        system_prompt = _SYSTEM_BASE.format(tone=tone)

        user_message = (
            f"Email to reply to:\n"
            f"From: {email.sender}\n"
            f"Subject: {email.subject}\n"
            f"Summary: {classification.summary}\n\n"
            f"Original message:\n{email.body[:EMAIL_BODY_MAX_CHARS]}"
        )

        response = self._client.models.generate_content(
            model=self._model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )

        assert response.text is not None, "Gemini returned empty response"
        reply: str = response.text.strip()
        logger.debug(
            f"Drafted reply for {email.message_id} (category={classification.category})"
        )
        return reply
