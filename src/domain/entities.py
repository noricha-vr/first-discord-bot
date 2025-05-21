from dataclasses import dataclass
from datetime import datetime

@dataclass
class ActiveThread:
    id: int
    discord_thread_id: int
    user_id: int
    channel_id: int
    created_at: datetime
    last_activity_at: datetime

@dataclass
class ChatMessage:
    id: int
    thread_db_id: int
    role: str
    content: str
    timestamp: datetime
