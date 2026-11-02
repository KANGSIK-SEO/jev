#!/usr/bin/env python3
"""
Apple Intelligence Offline Triage CLI
Run: python3 cli.py
"""
import sys
import os
import json
from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt

from models import MessageItem, TriageResult, IntelligenceBriefing
from service import LocalIntelligenceService

console = Console()

def print_banner(service: LocalIntelligenceService):
    installed = service.get_installed_models()
    is_model_ready = any(service.model_name in m for m in installed)
    engine_status = f"[green]온디바이스 LLM ({service.model_name}) 활성화[/green]" if is_model_ready else "[yellow]온디바이스 경량 엔진 (다운로드 완료 시 자동 전환)[/yellow]"

    banner_text = f"""[bold white]🍎 Local Intelligence (Apple Intelligence Style)[/bold white]
[cyan]와이파이 / 데이터 연결 없이 100% 기기 내부(On-Device)에서 동작하는 메시지 선별 & 요약 서비스[/cyan]

✈️  오프라인 환경 보장: [bold green]100% 로컬 (개인정보 외부 유출 없음)[/bold green]
🧠  추론 엔진 상태: {engine_status}
📱  지원 대상: 중요 문자(SMS), 중요 카카오톡, 중요 업무 이메일
"""
    console.print(Panel(banner_text, border_style="blue", title="[bold]Offline Intelligence Service[/bold]", subtitle="Privacy First"))

def display_briefing(briefing: IntelligenceBriefing, messages: List[MessageItem]):
    # 1. Executive Summary Panel (Apple Intelligence Style)
    summary_panel = Panel(
        f"[bold bright_white]{briefing.executive_summary}[/bold bright_white]\n\n"
        f"[dim]• 분석된 총 알림: {briefing.total_messages}개 | "
        f"[bold red]중요 알림: {briefing.important_count}개[/bold red] | "
        f"[dim]음소거/필터링: {briefing.ignored_count}개[/dim]",
        title="[bold yellow]✨ Apple Intelligence 브리핑 요약[/bold yellow]",
        border_style="yellow",
        padding=(1, 2)
    )
    console.print(summary_panel)
    console.print()

    # 2. Priority Notifications (중요 알림)
    msg_map = {m.id: m for m in messages}
    important_items = [r for r in briefing.triage_results if r.is_important]
    important_items.sort(key=lambda x: x.priority, reverse=True)

    if important_items:
        table = Table(title="[bold red]🚨 중요 우선순위 알림 (Priority Notifications)[/bold red]", border_style="red", show_header=True, header_style="bold magenta")
        table.add_column("우선순위", justify="center", width=10)
        table.add_column("출처/발신자", width=22)
        table.add_column("분류", width=12)
        table.add_column("AI 핵심 1줄 요약 & 조치 사항", style="white")

        badge_colors = {
            "긴급/장애": "bold red",
            "업무/요청": "bold cyan",
            "금융/보안": "bold yellow",
            "일정/약속": "bold green",
            "일반/잡담": "dim",
            "광고/스팸": "dim red"
        }

        priority_stars = {
            5: "★★★★★ (긴급)",
            4: "★★★★☆ (높음)",
            3: "★★★☆☆ (보통)",
            2: "★★☆☆☆",
            1: "★☆☆☆☆"
        }

        for item in important_items:
            orig = msg_map.get(item.message_id)
            source_badge = f"[{'green' if orig.source=='KAKAOTALK' else 'blue' if orig.source=='EMAIL' else 'yellow'}][{orig.source}][/]"
            sender_str = f"{source_badge} {orig.sender}\n[dim]({orig.timestamp})[/dim]"

            color = badge_colors.get(item.category, "white")
            cat_badge = f"[{color}]{item.category}[/]"
            p_text = priority_stars.get(item.priority, str(item.priority))

            action_text = f"\n[bold green]👉 할 일:[/] {item.action_required}" if item.action_required else ""
            summary_content = f"[bold]{item.one_line_summary}[/bold]{action_text}\n[dim italic]사유: {item.reason}[/dim italic]"

            table.add_row(p_text, sender_str, cat_badge, summary_content)

        console.print(table)
        console.print()

    # 3. Action Items Checklist
    if briefing.action_items:
        action_text = "\n".join([f"  [bold green]✓[/bold green] {act}" for act in briefing.action_items])
        action_panel = Panel(
            action_text,
            title="[bold green]📋 스마트 액션 아이템 (To-Do List)[/bold green]",
            border_style="green",
            padding=(1, 2)
        )
        console.print(action_panel)
        console.print()

    # 4. Filtered / Muted Notifications (단순 잡담/광고)
    ignored_items = [r for r in briefing.triage_results if not r.is_important]
    if ignored_items:
        ignored_table = Table(title="[dim]🔕 필터링된 알림 (광고, 단순 잡담, 배송완료 - 방해 금지 모드 자동 적용)[/dim]", border_style="dim", show_header=True)
        ignored_table.add_column("출처", width=12)
        ignored_table.add_column("발신자", width=20)
        ignored_table.add_column("분류", width=12)
        ignored_table.add_column("요약", style="dim")

        for item in ignored_items:
            orig = msg_map.get(item.message_id)
            ignored_table.add_row(orig.source, orig.sender, item.category, item.one_line_summary)

        console.print(ignored_table)
        console.print()

def run_demo(service: LocalIntelligenceService):
    sample_path = os.path.join(os.path.dirname(__file__), "sample_messages.json")
    with open(sample_path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    messages = [MessageItem(**item) for item in raw_list]
    console.print(f"[bold cyan]📥 총 {len(messages)}개의 샘플 알림(문자, 카톡, 이메일)을 수집하여 분석을 시작합니다...[/bold cyan]")
    
    with console.status("[bold green]로컬 추론 모델로 메시지 분류 및 요약 생성 중 (오프라인 모드)...[/bold green]"):
        briefing = service.process_all(messages)

    display_briefing(briefing, messages)

def run_interactive(service: LocalIntelligenceService):
    console.print("\n[bold cyan]✏️  직접 테스트할 메시지 정보를 입력하세요.[/bold cyan]")
    source = Prompt.ask("출처를 선택하세요", choices=["SMS", "KAKAOTALK", "EMAIL"], default="KAKAOTALK")
    sender = Prompt.ask("발신자 이름 또는 번호", default="부장님")
    subject = None
    if source == "EMAIL":
        subject = Prompt.ask("이메일 제목", default="긴급 일정 변경 안내")
    content = Prompt.ask("메시지 본문 내용", default="내일 오전 9시 회의자료 검토 부탁드립니다. 오늘 퇴근 전까지 회신주세요.")

    msg = MessageItem(
        id="user-input-1",
        source=source,
        sender=sender,
        timestamp="방금 전",
        subject=subject,
        content=content
    )

    with console.status("[bold green]로컬 AI 분석 중...[/bold green]"):
        result = service.analyze_message(msg)

    console.print("\n[bold yellow]=== 분석 결과 ===[/bold yellow]")
    console.print(f"• 중요도 판별: {'[bold red]🚨 중요 알림[/bold red]' if result.is_important else '[dim]일반 알림[/dim]'}")
    console.print(f"• 우선순위 점수: {result.priority} / 5")
    console.print(f"• 카테고리: {result.category}")
    console.print(f"• 핵심 요약: [bold]{result.one_line_summary}[/bold]")
    if result.action_required:
        console.print(f"• 추천 액션: [bold green]{result.action_required}[/bold green]")
    console.print(f"• 판단 근거: [dim]{result.reason}[/dim]\n")

def main():
    service = LocalIntelligenceService()
    print_banner(service)

    while True:
        console.print("[bold]원하시는 작업을 선택하세요:[/bold]")
        console.print("  [1] 📋 종합 데모 실행 (문자/카톡/이메일 샘플 일괄 요약)")
        console.print("  [2] ✏️  새로운 메시지 직접 입력해서 판별/요약하기")
        console.print("  [3] 🌐 로컬 웹 대시보드 실행 안내 (브라우저에서 보기)")
        console.print("  [q] 종료")
        
        choice = Prompt.ask("선택", choices=["1", "2", "3", "q"], default="1")
        if choice == "1":
            run_demo(service)
        elif choice == "2":
            run_interactive(service)
        elif choice == "3":
            console.print("\n[bold green]웹 대시보드 실행 방법:[/bold green]")
            console.print("다른 터미널 창에서 다음 명령어를 실행하면 브라우저(http://localhost:8000)에서 실시간으로 확인하실 수 있습니다:")
            console.print("  [cyan]python3 /Users/kangsikseo/local-intelligence/app.py[/cyan]\n")
        elif choice == "q":
            console.print("[dim]종료합니다.[/dim]")
            break

if __name__ == "__main__":
    main()
