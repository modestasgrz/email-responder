from google.genai.errors import ServerError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Retries on transient Gemini 503 UNAVAILABLE errors.
# Exponential backoff: 4s → 8s → 16s → 60s cap, 4 attempts total.
gemini_retry = retry(
    retry=retry_if_exception_type(ServerError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    reraise=True,
)
