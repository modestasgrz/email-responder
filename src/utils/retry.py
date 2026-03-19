from google.genai.errors import ClientError, ServerError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ServerError):
        return True
    if isinstance(exc, ClientError) and exc.code in (429, 499):
        return True
    return False


# Retries on transient Gemini 503 UNAVAILABLE and 429 RESOURCE_EXHAUSTED errors.
# Exponential backoff: 40s → 80s → 120s cap, 4 attempts total.
# Min 40s to respect Gemini's suggested retry delay on rate limits.
gemini_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=40, max=120),
    reraise=True,
)
