from datetime import datetime

from pydantic import BaseModel


class Email(BaseModel):
    message_id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    received_at: datetime
