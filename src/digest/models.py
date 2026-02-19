from enum import Enum

from pydantic import BaseModel


class NewsletterCategory(str, Enum):
    TECH_BUSINESS = "tech_business"
    MUSIC = "music"
    OTHER = "other"


class NewsItem(BaseModel):
    headline: str
    problem_or_impact: str
    user_sentiment: str
    source_url: str
    source_name: str


class DigestSection(BaseModel):
    category: NewsletterCategory
    items: list[NewsItem]
