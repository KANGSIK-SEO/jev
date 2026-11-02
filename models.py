"""
Data models for Offline Intelligence Service
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import json

@dataclass
class MessageItem:
    id: str
    source: str  # "SMS" | "KAKAOTALK" | "EMAIL"
    sender: str
    timestamp: str
    content: str
    subject: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "sender": self.sender,
            "timestamp": self.timestamp,
            "subject": self.subject,
            "content": self.content
        }

@dataclass
class TriageResult:
    message_id: str
    is_important: bool
    priority: int  # 1(낮음) ~ 5(최고 긴급)
    category: str  # "긴급/장애", "업무/요청", "금융/보안", "일정/약속", "일반/잡담", "광고/스팸"
    one_line_summary: str
    action_required: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "is_important": self.is_important,
            "priority": self.priority,
            "category": self.category,
            "one_line_summary": self.one_line_summary,
            "action_required": self.action_required,
            "reason": self.reason
        }

@dataclass
class IntelligenceBriefing:
    total_messages: int
    important_count: int
    ignored_count: int
    executive_summary: str
    action_items: List[str]
    triage_results: List[TriageResult] = field(default_factory=list)
