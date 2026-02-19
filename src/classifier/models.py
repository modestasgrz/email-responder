from enum import Enum

from pydantic import BaseModel


class EmailCategory(str, Enum):
    SUPPORT = "support"
    SALES = "sales"
    SPAM = "spam"
    NEWSLETTER = "newsletter"
    PERSONAL = "personal"
    UNKNOWN = "unknown"  # invoices, bookings, receipts, review requests — skipped


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
