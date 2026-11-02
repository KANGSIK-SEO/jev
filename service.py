"""
Core Engine for Offline Intelligence Service
Works 100% locally without Wi-Fi / Internet connection.
"""
import json
import re
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from models import MessageItem, TriageResult, IntelligenceBriefing
from prompts import SYSTEM_PROMPT, TRIAGE_PROMPT_TEMPLATE, BATCH_BRIEFING_PROMPT

class LocalIntelligenceService:
    def __init__(self, model_name: str = "qwen2.5:0.5b", base_url: str = "http://127.0.0.1:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def check_ollama_available(self) -> bool:
        """Check if local Ollama daemon is running."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def get_installed_models(self) -> List[str]:
        """List locally available models on device."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def _call_ollama(self, prompt: str, system: Optional[str] = None, json_mode: bool = True) -> str:
        """Call offline Ollama endpoint on 127.0.0.1 loopback."""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for factual precision
                "num_predict": 512,
            }
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=45) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            return res_json.get("response", "")

    def analyze_message_llm(self, msg: MessageItem) -> TriageResult:
        """Analyze a single message using local SLM."""
        subject_line = f"- 제목: {msg.subject}" if msg.subject else ""
        prompt = TRIAGE_PROMPT_TEMPLATE.format(
            source=msg.source,
            sender=msg.sender,
            timestamp=msg.timestamp,
            subject_line=subject_line,
            content=msg.content
        )

        raw_output = self._call_ollama(prompt, system=SYSTEM_PROMPT, json_mode=True)
        try:
            data = json.loads(raw_output)
            return TriageResult(
                message_id=msg.id,
                is_important=bool(data.get("is_important", False)),
                priority=int(data.get("priority", 1)),
                category=str(data.get("category", "일반/잡담")),
                one_line_summary=str(data.get("one_line_summary", msg.content[:40])),
                action_required=data.get("action_required"),
                reason=str(data.get("reason", "로컬 SLM 자동 분석"))
            )
        except Exception as e:
            # Fallback if JSON parsing fails
            return self._heuristic_fallback(msg, f"JSON 파싱 실패 폴백: {str(e)}")

    def _heuristic_fallback(self, msg: MessageItem, reason_prefix: str = "온디바이스 룰베이스 필터") -> TriageResult:
        """Deterministic on-device heuristic analyzer (Zero latency fallback)."""
        text = f"{msg.subject or ''} {msg.content}".lower()
        sender = msg.sender.lower()

        # 1. Spams & Ads
        if "(광고)" in text or "리딩방" in text or "무료거부" in text or "상한가" in text:
            return TriageResult(
                message_id=msg.id,
                is_important=False,
                priority=1,
                category="광고/스팸",
                one_line_summary=f"[{msg.source}] 광고 스팸 메시지 차단됨",
                action_required=None,
                reason=f"{reason_prefix} (광고 키워드 감지)"
            )

        # 2. Critical & Server alerts
        if any(w in text for w in ["alarm", "critical", "cpu >", "장애", "오류", "긴급"]):
            return TriageResult(
                message_id=msg.id,
                is_important=True,
                priority=5,
                category="긴급/장애",
                one_line_summary=f"[{msg.source}] 시스템/서버 임계치 초과 긴급 경고",
                action_required="운영 서버 상태 점검 및 트래픽/스케일아웃 조치",
                reason=f"{reason_prefix} (긴급 장애 알림)"
            )

        # 3. Financial & Security
        if any(w in text for w in ["해외승인", "결제", "카드", "승인", "인증번호", "본인사용"]):
            return TriageResult(
                message_id=msg.id,
                is_important=True,
                priority=4,
                category="금융/보안",
                one_line_summary=f"[{msg.source}] {msg.sender} 결제 또는 승인 내역 발생",
                action_required="본인 결제 여부 확인 (도용 의심 시 즉시 고객센터 문의)",
                reason=f"{reason_prefix} (금융 결제 및 보안 문자)"
            )

        # 4. Work & Deadline & Meeting
        if any(w in text for w in ["보고", "회의", "검토", "서명", "회신", "공유", "마감", "까지"]):
            return TriageResult(
                message_id=msg.id,
                is_important=True,
                priority=4,
                category="업무/요청",
                one_line_summary=f"[{msg.source}] {msg.sender}의 업무 요청 및 마감 회신 건",
                action_required="요청 내용 검토 후 지정 기한 내 피드백/회신",
                reason=f"{reason_prefix} (업무 요청 및 기한 포함)"
            )

        # 5. Delivery notifications
        if "배송 완료" in text or "택배" in text:
            return TriageResult(
                message_id=msg.id,
                is_important=False,
                priority=2,
                category="일반/잡담",
                one_line_summary=f"[{msg.source}] 주문 상품 배송 완료 알림",
                action_required=None,
                reason=f"{reason_prefix} (단순 배송 확인 알림)"
            )

        # 6. Personal Important (Family)
        if any(w in sender for w in ["어머니", "엄마", "아버지", "아빠", "가족"]):
            return TriageResult(
                message_id=msg.id,
                is_important=True,
                priority=3,
                category="일정/약속",
                one_line_summary=f"{msg.sender}의 주말 방문/일정 조율 연락",
                action_required="주말 일정 확인 후 연락 회신",
                reason=f"{reason_prefix} (가족 주요 연락)"
            )

        # Default casual
        return TriageResult(
            message_id=msg.id,
            is_important=False,
            priority=1,
            category="일반/잡담",
            one_line_summary=f"[{msg.source}] {msg.sender}: {msg.content[:30]}...",
            action_required=None,
            reason=f"{reason_prefix} (일반 대화/단순 연락)"
        )

    def analyze_message(self, msg: MessageItem) -> TriageResult:
        """Analyze message, using local Ollama if model ready, else fast heuristic."""
        installed = self.get_installed_models()
        # Check if our target model (e.g. qwen2.5:1.5b) is available locally
        model_ready = any(self.model_name in m for m in installed)

        if self.check_ollama_available() and model_ready:
            try:
                return self.analyze_message_llm(msg)
            except Exception as e:
                return self._heuristic_fallback(msg, f"LLM 일시 오류로 온디바이스 폴백: {e}")
        else:
            return self._heuristic_fallback(msg, "온디바이스 고속 엔진")

    def process_all(self, messages: List[MessageItem]) -> IntelligenceBriefing:
        """Process list of messages, filter important ones, and generate briefing."""
        triage_results: List[TriageResult] = []
        important_results: List[TriageResult] = []
        action_items: List[str] = []

        for msg in messages:
            res = self.analyze_message(msg)
            triage_results.append(res)
            if res.is_important:
                important_results.append(res)
                if res.action_required:
                    action_items.append(f"[{res.category}] {res.action_required} (발신: {msg.sender})")

        # Sort important messages by priority descending
        important_results.sort(key=lambda x: x.priority, reverse=True)

        # Executive summary generation
        if important_results:
            summary_lines = []
            for r in important_results[:4]:
                summary_lines.append(f"- {r.one_line_summary}")

            # Try generating briefing via LLM if ready
            installed = self.get_installed_models()
            model_ready = any(self.model_name in m for m in installed)
            if self.check_ollama_available() and model_ready:
                try:
                    prompt = BATCH_BRIEFING_PROMPT.format(important_messages_text="\n".join(summary_lines))
                    executive_summary = self._call_ollama(prompt, system=SYSTEM_PROMPT, json_mode=False).strip()
                except Exception:
                    executive_summary = f"총 {len(messages)}개의 알림 중 {len(important_results)}개의 중요 연락이 있습니다. 시급한 업무와 금융/장애 알림을 먼저 확인하세요."
            else:
                executive_summary = f"총 {len(messages)}개의 메시지 중 {len(important_results)}개의 긴급/중요 알림이 감지되었습니다. 주요 업무 및 결제 알림을 우선 확인하세요."
        else:
            executive_summary = "현재 도착한 메시지 중 즉각적인 조치가 필요한 긴급 메시지는 없습니다."

        return IntelligenceBriefing(
            total_messages=len(messages),
            important_count=len(important_results),
            ignored_count=len(messages) - len(important_results),
            executive_summary=executive_summary,
            action_items=action_items,
            triage_results=triage_results
        )
