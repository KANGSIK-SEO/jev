"""
Apple Intelligence Offline Web Dashboard
FastAPI + On-Device Local Inference
Run: python3 app.py
Open: http://localhost:8000
"""
import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List

from models import MessageItem, TriageResult, IntelligenceBriefing
from service import LocalIntelligenceService
from crawler import MultiChannelAutoCrawler

app = FastAPI(title="JEV × Wirelog Auto-Sensing & Local Intelligence Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
service = LocalIntelligenceService()
crawler = MultiChannelAutoCrawler()

# In-memory message store initialized with sample data
SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "sample_messages.json")
with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
    initial_data = json.load(f)
current_messages = [MessageItem(**item) for item in initial_data]

class NewMessageRequest(BaseModel):
    source: str
    sender: str
    content: str
    subject: Optional[str] = None

class ImapConfigRequest(BaseModel):
    host: str = "imap.gmail.com"
    port: int = 993
    user: str
    password: str

@app.get("/api/sensor/crawl")
def trigger_auto_crawl():
    """문자(chat.db), 이메일(IMAP), 카카오톡 폴더를 자동 센싱·크롤링하여 중요도 선별 결과 반환"""
    newly_sensed = crawler.sense_all_channels()
    added_items = []
    for raw in newly_sensed:
        msg = MessageItem(
            id=raw["id"],
            source=raw["source"],
            sender=raw["sender"],
            timestamp=raw["timestamp"],
            subject=raw.get("subject"),
            content=raw["content"],
        )
        current_messages.insert(0, msg)
        triage = service._heuristic_fallback(msg)
        added_items.append({
            "raw": raw,
            "triage": triage.to_dict(),
        })
    return {
        "status": "ok",
        "newly_sensed_count": len(added_items),
        "stats": crawler.stats,
        "items": added_items,
    }

@app.post("/api/sensor/config/imap")
def configure_imap_sensor(cfg: ImapConfigRequest):
    crawler.imap_config = {
        "host": cfg.host,
        "port": cfg.port,
        "user": cfg.user,
        "password": cfg.password,
        "enabled": bool(cfg.user and cfg.password),
    }
    return {"status": "configured", "host": cfg.host, "user": cfg.user}

@app.post("/api/sensor/webhook")
def receive_mobile_webhook(req: NewMessageRequest):
    """아이폰 단축어(Shortcuts) 자동화 또는 안드로이드 NotificationListenerService에서 무인 전송"""
    new_id = f"hook-{len(current_messages) + 1:04d}"
    msg = MessageItem(
        id=new_id,
        source=req.source,
        sender=req.sender,
        timestamp="방금 전",
        subject=req.subject,
        content=req.content,
    )
    current_messages.insert(0, msg)
    triage = service._heuristic_fallback(msg)
    crawler.stats["total_sensed"] += 1
    return {"message": msg.to_dict(), "triage": triage.to_dict()}

@app.get("/jev", response_class=HTMLResponse)
def jev_pwa_page():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/status")
def get_status():
    installed = service.get_installed_models()
    is_ready = any(service.model_name in m for m in installed)
    return {
        "status": "online",
        "offline_ready": True,
        "engine": service.model_name if is_ready else "온디바이스 하이브리드 고속 엔진",
        "llm_loaded": is_ready,
        "installed_models": installed
    }

@app.get("/api/messages")
def get_messages():
    return [m.to_dict() for m in current_messages]

@app.post("/api/messages")
def add_message(req: NewMessageRequest):
    new_id = f"msg-{len(current_messages) + 1:03d}"
    msg = MessageItem(
        id=new_id,
        source=req.source,
        sender=req.sender,
        timestamp="방금 전",
        subject=req.subject,
        content=req.content
    )
    current_messages.append(msg)
    return msg.to_dict()

@app.get("/api/briefing")
def get_briefing():
    briefing = service.process_all(current_messages)
    return {
        "total_messages": briefing.total_messages,
        "important_count": briefing.important_count,
        "ignored_count": briefing.ignored_count,
        "executive_summary": briefing.executive_summary,
        "action_items": briefing.action_items,
        "triage_results": [r.to_dict() for r in briefing.triage_results]
    }

@app.get("/mobile", response_class=HTMLResponse)
def mobile_page():
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>스마트폰 온디바이스 알림 인텔리전스</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
    body {
      background: #000;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", Pretendard, sans-serif;
      padding: 16px;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    /* iOS Dynamic Island & Status Bar */
    .status-bar {
      display: flex; justify-content: space-between; align-items: center;
      font-size: 13px; font-weight: 600; padding: 4px 8px 16px;
    }
    .offline-tag {
      background: rgba(48, 209, 88, 0.2);
      border: 1px solid #30D158;
      color: #30D158;
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 12px;
      display: flex; align-items: center; gap: 4px;
    }
    /* Apple Intelligence Glow Card */
    .ai-pill {
      background: linear-gradient(135deg, rgba(255, 55, 95, 0.25), rgba(191, 90, 242, 0.3), rgba(10, 132, 255, 0.3));
      border: 1.5px solid rgba(191, 90, 242, 0.6);
      border-radius: 20px;
      padding: 16px;
      margin-bottom: 20px;
      backdrop-filter: blur(20px);
      box-shadow: 0 4px 24px rgba(191, 90, 242, 0.25);
    }
    .ai-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    .ai-title { display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 14px; color: #fff; }
    .ai-summary { font-size: 13px; line-height: 1.5; color: #e5e7eb; margin-bottom: 10px; }
    .action-item {
      background: rgba(0, 0, 0, 0.4);
      border-left: 3px solid #30D158;
      padding: 8px 10px;
      border-radius: 6px;
      font-size: 12px;
      margin-top: 6px;
      color: #fff;
    }

    .section-title {
      font-size: 12px;
      font-weight: 700;
      color: #9ca3af;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin: 16px 0 10px;
    }

    .card {
      background: rgba(30, 30, 35, 0.85);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 16px;
      padding: 14px;
      margin-bottom: 10px;
      backdrop-filter: blur(10px);
    }
    .card.important { border-left: 4px solid #0A84FF; }
    .card.critical { border-left: 4px solid #FF453A; }
    .card.muted { opacity: 0.5; }

    .card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .source-badge {
      font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px;
    }
    .source-kakao { background: #FEE500; color: #000; }
    .source-sms { background: #FF9F0A; color: #000; }
    .source-email { background: #0A84FF; color: #fff; }

    .sender { font-size: 13px; font-weight: 600; margin-left: 6px; }
    .time { font-size: 11px; color: #8e8e93; }
    .summary-text { font-size: 13px; font-weight: 600; color: #fff; margin-bottom: 4px; }
    .action-text { font-size: 11px; color: #30D158; margin-top: 4px; }
    .content-preview { font-size: 12px; color: #8e8e93; margin-top: 4px; }

    /* Bottom Input Bar */
    .quick-bar {
      margin-top: auto;
      padding-top: 16px;
    }
    .input-row { display: flex; gap: 8px; }
    .quick-input {
      flex: 1;
      background: #1c1c1e;
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 20px;
      padding: 10px 14px;
      color: #fff;
      font-size: 13px;
    }
    .quick-btn {
      background: #0A84FF;
      color: #fff;
      border: none;
      padding: 0 16px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="status-bar">
    <span>13:55</span>
    <div class="offline-tag">✈️ 오프라인 온디바이스</div>
    <span>⚡ 100%</span>
  </div>

  <!-- Apple Intelligence Summary Card -->
  <div class="ai-pill">
    <div class="ai-header">
      <div class="ai-title">✨ 스마트폰 AI 요약</div>
      <span style="font-size: 11px; color: #d1d5db;" id="statBadge">분석 중...</span>
    </div>
    <div class="ai-summary" id="aiSummary">알림을 온디바이스로 처리 중입니다...</div>
    <div id="aiActions"></div>
  </div>

  <div class="section-title">🚨 우선순위 알림 (중요 문자/카톡/메일)</div>
  <div id="priorityList"></div>

  <div class="section-title">🔕 음소거된 알림 (잡담 / 광고)</div>
  <div id="mutedList"></div>

  <div class="quick-bar">
    <div class="input-row">
      <input type="text" id="mContent" class="quick-input" placeholder="새 문자/카톡 내용 입력 테스트..." value="팀장님: 3시까지 수정자료 공유바람" />
      <button class="quick-btn" onclick="sendMobileMsg()">분석</button>
    </div>
  </div>

  <script>
    async function loadData() {
      const [msgRes, briefRes] = await Promise.all([
        fetch('/api/messages').then(r => r.json()),
        fetch('/api/briefing').then(r => r.json())
      ]);

      document.getElementById('aiSummary').innerText = briefRes.executive_summary;
      document.getElementById('statBadge').innerText = `${briefRes.important_count}개 중요 알림 선별`;

      const actionsDiv = document.getElementById('aiActions');
      actionsDiv.innerHTML = '';
      (briefRes.action_items || []).forEach(act => {
        const item = document.createElement('div');
        item.className = 'action-item';
        item.innerHTML = `✓ ${act}`;
        actionsDiv.appendChild(item);
      });

      const msgMap = {};
      msgRes.forEach(m => msgMap[m.id] = m);

      const pList = document.getElementById('priorityList');
      const mList = document.getElementById('mutedList');
      pList.innerHTML = '';
      mList.innerHTML = '';

      briefRes.triage_results.forEach(r => {
        const orig = msgMap[r.message_id] || {};
        const card = document.createElement('div');
        const isCrit = r.priority >= 5;
        card.className = `card ${r.is_important ? (isCrit ? 'critical' : 'important') : 'muted'}`;

        let sourceClass = 'source-sms';
        if (orig.source === 'KAKAOTALK') sourceClass = 'source-kakao';
        if (orig.source === 'EMAIL') sourceClass = 'source-email';

        const actionHtml = r.action_required ? `<div class="action-text">👉 ${r.action_required}</div>` : '';

        card.innerHTML = `
          <div class="card-top">
            <div>
              <span class="source-badge ${sourceClass}">${orig.source || 'SMS'}</span>
              <span class="sender">${orig.sender || ''}</span>
            </div>
            <span class="time">${orig.timestamp || ''}</span>
          </div>
          <div class="summary-text">${r.one_line_summary}</div>
          ${actionHtml}
          <div class="content-preview">${orig.content || ''}</div>
        `;

        if (r.is_important) pList.appendChild(card);
        else mList.appendChild(card);
      });
    }

    async function sendMobileMsg() {
      const text = document.getElementById('mContent').value;
      if (!text.trim()) return;
      await fetch('/api/messages', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ source: 'KAKAOTALK', sender: '카카오톡', content: text })
      });
      document.getElementById('mContent').value = '';
      loadData();
    }

    window.addEventListener('DOMContentLoaded', loadData);
  </script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def index_page():
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Apple Intelligence - 오프라인 메시지 요약 & 선별</title>
  <style>
    :root {
      --bg: #0f1117;
      --card-bg: rgba(26, 31, 44, 0.75);
      --card-border: rgba(255, 255, 255, 0.1);
      --accent: #0A84FF;
      --accent-glow: rgba(10, 132, 255, 0.35);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --danger: #FF453A;
      --warning: #FF9F0A;
      --success: #30D158;
      --purple: #BF5AF2;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Pretendard", sans-serif; }
    body {
      background: radial-gradient(circle at top center, #1b2038 0%, var(--bg) 70%);
      color: var(--text);
      min-height: 100vh;
      padding: 24px;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 24px;
    }
    .logo-area { display: flex; align-items: center; gap: 12px; }
    .logo-badge {
      background: linear-gradient(135deg, #FF375F, #BF5AF2, #0A84FF);
      width: 40px; height: 40px; border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 22px;
    }
    .header-title h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
    .header-title p { font-size: 13px; color: var(--text-muted); }
    .status-badge {
      display: flex; align-items: center; gap: 8px;
      background: rgba(48, 209, 88, 0.15);
      border: 1px solid rgba(48, 209, 88, 0.4);
      color: #30D158;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
    }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #30D158; box-shadow: 0 0 8px #30D158; }

    /* Summary Glow Box */
    .glow-card {
      background: linear-gradient(135deg, rgba(30, 41, 75, 0.9), rgba(15, 23, 42, 0.8));
      border: 1px solid rgba(191, 90, 242, 0.4);
      border-radius: 18px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 20px rgba(191, 90, 242, 0.15);
      position: relative;
      overflow: hidden;
    }
    .glow-card::before {
      content: "";
      position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
      background: conic-gradient(transparent, rgba(10, 132, 255, 0.15), rgba(191, 90, 242, 0.2), transparent 40%);
      animation: rotate 12s linear infinite;
      z-index: 0; pointer-events: none;
    }
    @keyframes rotate { 100% { transform: rotate(360deg); } }
    .glow-content { position: relative; z-index: 1; }
    .glow-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .glow-title { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 700; color: #fdfdfd; }
    .exec-summary-text { font-size: 15px; line-height: 1.6; color: #e2e8f0; margin-bottom: 16px; }

    .action-chips { display: flex; flex-direction: column; gap: 8px; }
    .action-chip {
      background: rgba(255, 255, 255, 0.06);
      border-left: 3px solid #30D158;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 13px;
      display: flex; align-items: center; gap: 8px;
    }

    /* Grid Layout */
    .dashboard-grid { display: grid; grid-template-columns: 1fr 340px; gap: 24px; }
    @media (max-width: 900px) { .dashboard-grid { grid-template-columns: 1fr; } }

    .section-title { font-size: 15px; font-weight: 600; margin-bottom: 14px; display: flex; align-items: center; gap: 6px; }
    .notification-list { display: flex; flex-direction: column; gap: 12px; }

    .notif-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 16px;
      transition: all 0.2s ease;
      backdrop-filter: blur(12px);
    }
    .notif-card:hover { transform: translateY(-2px); border-color: rgba(255, 255, 255, 0.25); }
    .notif-card.important { border-left: 4px solid var(--accent); }
    .notif-card.critical { border-left: 4px solid var(--danger); }
    .notif-card.muted { opacity: 0.55; }

    .notif-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .notif-meta { display: flex; align-items: center; gap: 8px; }
    .tag { font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; }
    .tag-sms { background: rgba(255, 159, 10, 0.2); color: #FF9F0A; }
    .tag-kakao { background: rgba(254, 229, 0, 0.2); color: #FEE500; }
    .tag-email { background: rgba(10, 132, 255, 0.2); color: #0A84FF; }
    .tag-p5 { background: rgba(255, 69, 58, 0.2); color: #FF453A; }
    .tag-p4 { background: rgba(255, 159, 10, 0.2); color: #FF9F0A; }

    .sender-name { font-size: 14px; font-weight: 600; }
    .notif-time { font-size: 12px; color: var(--text-muted); }
    .notif-summary { font-size: 14px; font-weight: 500; color: #fff; margin-bottom: 6px; }
    .notif-action { font-size: 12px; color: #30D158; background: rgba(48, 209, 88, 0.1); padding: 6px 10px; border-radius: 6px; margin-top: 6px; display: inline-block; }
    .notif-raw { font-size: 12px; color: var(--text-muted); line-height: 1.4; margin-top: 6px; }

    /* Controls Panel */
    .control-box {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 18px;
      height: fit-content;
      backdrop-filter: blur(12px);
    }
    .btn {
      width: 100%;
      background: linear-gradient(135deg, #0A84FF, #0066CC);
      color: white; border: none;
      padding: 12px; border-radius: 10px;
      font-size: 14px; font-weight: 600;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center; gap: 8px;
      transition: opacity 0.2s;
    }
    .btn:hover { opacity: 0.9; }
    .input-group { margin-top: 14px; }
    .input-group label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
    .input-control {
      width: 100%; background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 10px; color: white; font-size: 13px;
    }
    textarea.input-control { resize: vertical; min-height: 80px; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo-area">
        <div class="logo-badge">🍎</div>
        <div class="header-title">
          <h1>Apple Intelligence - 오프라인 인텔리전스</h1>
          <p>Wi-Fi 및 네트워크 연결 없이 100% 온디바이스에서 동작하는 메시지 선별 및 요약 비서</p>
        </div>
      </div>
      <div class="status-badge">
        <div class="status-dot"></div>
        <span id="offlineStatus">✈️ 온디바이스 100% 로컬 동작 중</span>
      </div>
    </header>

    <!-- Executive Briefing Glow Panel -->
    <div class="glow-card">
      <div class="glow-content">
        <div class="glow-header">
          <div class="glow-title">
            <span>✨</span>
            <span>Apple Intelligence 데일리 브리핑 요약</span>
          </div>
          <span style="font-size: 12px; color: var(--text-muted);" id="briefingStats">분석 중...</span>
        </div>
        <p class="exec-summary-text" id="execSummary">수신된 알림들을 로컬 SLM 추론 엔진으로 분석 중입니다...</p>
        <div class="action-chips" id="actionChips"></div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="dashboard-grid">
      <!-- Left Column: Messages -->
      <div>
        <div class="section-title">🚨 우선순위 중요 알림 (Priority Notifications)</div>
        <div class="notification-list" id="importantList">
          <p style="color: var(--text-muted); font-size: 13px;">알림을 불러오는 중...</p>
        </div>

        <div class="section-title" style="margin-top: 28px; color: var(--text-muted);">
          🔕 필터링/음소거된 일반 알림 (방해 금지 모드 자동 적용)
        </div>
        <div class="notification-list" id="mutedList"></div>
      </div>

      <!-- Right Column: Quick Test / Controls -->
      <div>
        <div class="control-box">
          <h3 style="font-size: 14px; font-weight: 600; margin-bottom: 12px;">⚡ 새 메시지 즉시 테스트</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">임의의 카톡이나 문자, 이메일을 입력하면 오프라인 AI가 즉시 분류하고 요약합니다.</p>
          
          <div class="input-group">
            <label>출처</label>
            <select id="msgSource" class="input-control">
              <option value="KAKAOTALK">카카오톡</option>
              <option value="SMS">문자(SMS)</option>
              <option value="EMAIL">이메일</option>
            </select>
          </div>
          <div class="input-group">
            <label>발신자</label>
            <input type="text" id="msgSender" class="input-control" value="직장 상사" />
          </div>
          <div class="input-group">
            <label>메시지 본문</label>
            <textarea id="msgContent" class="input-control" placeholder="메시지 내용을 붙여넣으세요...">오후 4시 긴급 클라이언트 미팅 들어오셔야 합니다. 관련 보고서 지금 확인해주세요.</textarea>
          </div>
          
          <button class="btn" style="margin-top: 14px;" onclick="addAndAnalyze()">
            <span>➕</span> 메시지 추가 & AI 분석
          </button>
          <button class="btn" style="margin-top: 8px; background: rgba(255, 255, 255, 0.08);" onclick="loadBriefing()">
            <span>🔄</span> 전체 다시 브리핑하기
          </button>
        </div>
      </div>
    </div>
  </div>

  <script>
    async function loadBriefing() {
      try {
        const [statusRes, msgRes, briefRes] = await Promise.all([
          fetch('/api/status').then(r => r.json()),
          fetch('/api/messages').then(r => r.json()),
          fetch('/api/briefing').then(r => r.json())
        ]);

        document.getElementById('offlineStatus').innerText = `✈️ 온디바이스 (${statusRes.engine})`;
        document.getElementById('execSummary').innerText = briefRes.executive_summary;
        document.getElementById('briefingStats').innerText = `총 ${briefRes.total_messages}개 중 ${briefRes.important_count}개 중요 알림 선별됨`;

        // Render Action Items
        const actionChips = document.getElementById('actionChips');
        actionChips.innerHTML = '';
        if (briefRes.action_items && briefRes.action_items.length > 0) {
          briefRes.action_items.forEach(act => {
            const div = document.createElement('div');
            div.className = 'action-chip';
            div.innerHTML = `<strong>✓</strong> ${act}`;
            actionChips.appendChild(div);
          });
        }

        // Render Messages
        const msgMap = {};
        msgRes.forEach(m => msgMap[m.id] = m);

        const importantList = document.getElementById('importantList');
        const mutedList = document.getElementById('mutedList');
        importantList.innerHTML = '';
        mutedList.innerHTML = '';

        briefRes.triage_results.forEach(res => {
          const orig = msgMap[res.message_id] || {};
          const card = document.createElement('div');
          
          let tagClass = 'tag-sms';
          if (orig.source === 'KAKAOTALK') tagClass = 'tag-kakao';
          if (orig.source === 'EMAIL') tagClass = 'tag-email';

          const isCrit = res.priority >= 5;
          card.className = `notif-card ${res.is_important ? (isCrit ? 'critical' : 'important') : 'muted'}`;

          const priorityBadge = res.priority >= 4 ? `<span class="tag tag-p5">우선순위 ★${res.priority}</span>` : '';
          const actionHtml = res.action_required ? `<div class="notif-action">👉 ${res.action_required}</div>` : '';

          card.innerHTML = `
            <div class="notif-header">
              <div class="notif-meta">
                <span class="tag ${tagClass}">${orig.source || 'MSG'}</span>
                <span class="sender-name">${orig.sender || '발신자'}</span>
                ${priorityBadge}
                <span class="tag" style="background: rgba(255,255,255,0.08);">${res.category}</span>
              </div>
              <div class="notif-time">${orig.timestamp || ''}</div>
            </div>
            <div class="notif-summary">${res.one_line_summary}</div>
            ${actionHtml}
            <div class="notif-raw">${orig.subject ? '<strong>[' + orig.subject + ']</strong> ' : ''}${orig.content || ''}</div>
          `;

          if (res.is_important) {
            importantList.appendChild(card);
          } else {
            mutedList.appendChild(card);
          }
        });

      } catch (err) {
        console.error(err);
      }
    }

    async function addAndAnalyze() {
      const source = document.getElementById('msgSource').value;
      const sender = document.getElementById('msgSender').value;
      const content = document.getElementById('msgContent').value;

      if (!content.trim()) return alert('메시지 내용을 입력하세요.');

      await fetch('/api/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, sender, content })
      });

      document.getElementById('msgContent').value = '';
      loadBriefing();
    }

    // Auto load on start
    window.addEventListener('DOMContentLoaded', loadBriefing);
  </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    print("\n📱 스마트폰에서 접속 시:")
    print("   👉 http://192.168.123.135:8000/mobile")
    print("💻 데스크탑 브라우저에서 접속 시:")
    print("   👉 http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)

