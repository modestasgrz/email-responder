from enum import Enum

from pydantic import BaseModel


class EmailCategory(str, Enum):
    SUPPORT = "support"
    SALES = "sales"
    SPAM = "spam"
    NEWSLETTER = "newsletter"
    PERSONAL = "personal"
    INVOICE = "invoice"  # payment CTA — housing tax, insurance, digital subscriptions
    UNKNOWN = "unknown"  # bookings, receipts, review requests, automated notifications


class EmailPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ClassificationResult(BaseModel):
    category: EmailCategory
    priority: EmailPriority
    summary: str
    needs_reply: bool
    reasoning: str
