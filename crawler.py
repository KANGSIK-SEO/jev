"""
JEV × Wirelog — Multi-Channel Automatic Sensor & Crawler Daemon
자동으로 매일 쏟아지는 문자(SMS/iMessage), 카카오톡(KakaoTalk), 이메일(IMAP/Mail)을
백그라운드에서 센싱·크롤링하여 Wirelog Datalog 엔진으로 필터링 후 중요 1줄 요약만 추출합니다.

지원 센서(Sensors):
1. EmailIMAPSensor      : Gmail / Naver / Daum / iCloud IMAP 서버 실시간 미열람 메일 크롤링
2. MacOSMessagesSensor  : macOS ~/Library/Messages/chat.db (아이폰 문자 메시지 전달 연동) 자동 센싱
3. MacOSNotificationSensor: macOS 알림 센터 DB (카카오톡 com.kakao.talk 실시간 알림) 자동 센싱
4. KakaoFolderWatcher   : 카카오톡 대화 내보내기 폴더(~/Downloads 등) 자동 감지 크롤러
5. WebhookIngestSensor  : iPhone 단축어(Shortcuts) 무인 자동화 / Android NotificationListenerService 웹훅 수신
"""

import os
import re
import glob
import time
import json
import imaplib
import sqlite3
import email
from email.header import decode_header
from datetime import datetime
from typing import List, Dict, Any, Optional


class MultiChannelAutoCrawler:
    def __init__(self, watch_dirs: Optional[List[str]] = None):
        self.seen_ids = set()
        self.recent_items: List[Dict[str, Any]] = []
        self.crawl_logs: List[Dict[str, Any]] = []
        self.watch_dirs = watch_dirs or [
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Documents/KakaoTalk Downloads"),
        ]
        self.imap_config: Dict[str, Any] = {
            "host": os.environ.get("JEV_IMAP_HOST", "imap.gmail.com"),
            "port": int(os.environ.get("JEV_IMAP_PORT", "993")),
            "user": os.environ.get("JEV_IMAP_USER", ""),
            "password": os.environ.get("JEV_IMAP_PASS", ""),
            "enabled": bool(os.environ.get("JEV_IMAP_USER") and os.environ.get("JEV_IMAP_PASS")),
        }
        self.stats = {
            "total_sensed": 0,
            "sms_sensed": 0,
            "kakao_sensed": 0,
            "email_sensed": 0,
            "spam_blocked": 0,
            "noise_muted": 0,
            "important_extracted": 0,
            "last_crawl_at": None,
        }

    def _log_event(self, channel: str, sender: str, preview: str, decision: str, score: int = 0):
        entry = {
            "id": f"log_{int(time.time() * 1000)}_{len(self.crawl_logs)}",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "channel": channel,
            "sender": sender,
            "preview": preview[:60] + ("..." if len(preview) > 60 else ""),
            "decision": decision,  # 'URGENT' | 'IMPORTANT' | 'MUTED_NOISE' | 'BLOCKED_SPAM'
            "score": score,
        }
        self.crawl_logs.insert(0, entry)
        self.crawl_logs = self.crawl_logs[:100]

    # ------------------------------------------------------------------
    # 1. 이메일(Email) IMAP 실시간 크롤러 (Gmail / Naver / iCloud 등)
    # ------------------------------------------------------------------
    # 다중 IMAP 계정: ~/.jev/email_accounts.json (Git에 올라가지 않는 로컬 파일)
    ACCOUNTS_PATH = os.path.expanduser("~/.jev/email_accounts.json")

    def load_imap_accounts(self) -> List[Dict[str, Any]]:
        accounts = []
        if self.imap_config.get("enabled"):
            accounts.append(dict(self.imap_config))
        try:
            with open(self.ACCOUNTS_PATH, "r", encoding="utf-8") as f:
                for a in json.load(f):
                    if a.get("user") and a.get("password"):
                        accounts.append({"host": a.get("host", "imap.gmail.com"), "port": int(a.get("port", 993)),
                                         "user": a["user"], "password": a["password"].replace(" ", ""), "enabled": True})
        except Exception:
            pass
        # ~/Desktop/.env 의 JEV_* 변수 (Gmail / Naver / 기타)
        env = {}
        try:
            with open(os.path.expanduser("~/Desktop/.env"), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
        presets = [("GMAIL", "imap.gmail.com"), ("NAVER", "imap.naver.com"),
                   ("OTHER1", None), ("OTHER2", None)]
        for key, default_host in presets:
            user, pw = env.get(f"JEV_{key}_USER"), env.get(f"JEV_{key}_PW")
            host = env.get(f"JEV_{key}_HOST") or default_host
            if user and pw and host and not any(a["user"] == user for a in accounts):
                accounts.append({"host": host, "port": int(env.get(f"JEV_{key}_PORT", 993)),
                                 "user": user, "password": pw.replace(" ", ""), "enabled": True})
        return accounts

    def crawl_all_imap_accounts(self, limit: int = 15) -> List[Dict[str, Any]]:
        results = []
        original = self.imap_config
        for acc in self.load_imap_accounts():
            self.imap_config = acc
            results.extend(self.crawl_imap_emails(limit))
        self.imap_config = original
        return results

    def crawl_imap_emails(self, limit: int = 15) -> List[Dict[str, Any]]:
        if not self.imap_config.get("enabled"):
            return []

        results = []
        try:
            mail = imaplib.IMAP4_SSL(self.imap_config["host"], self.imap_config["port"])
            mail.login(self.imap_config["user"], self.imap_config["password"])
            mail.select("INBOX")

            status, data = mail.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                status, data = mail.search(None, "ALL")

            mail_ids = data[0].split()[-limit:]
            for m_id in reversed(mail_ids):
                uid = f"imap_{self.imap_config['user']}_{m_id.decode()}"
                if uid in self.seen_ids:
                    continue

                status, msg_data = mail.fetch(m_id, "(RFC822)")
                if status != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = self._decode_mime_words(msg.get("Subject", "(제목 없음)"))
                        sender = self._decode_mime_words(msg.get("From", "알 수 없음"))
                        body = self._extract_email_body(msg)
                        full_text = f"{subject}\n{body}".strip()

                        self.seen_ids.add(uid)
                        self.stats["total_sensed"] += 1
                        self.stats["email_sensed"] += 1
                        results.append({
                            "id": uid,
                            "source": "이메일",
                            "channel": "email",
                            "sender": sender[:40],
                            "account": self.imap_config["user"],
                            "subject": subject,
                            "content": full_text[:500],
                            "timestamp": datetime.now().strftime("%H:%M"),
                        })
            mail.logout()
        except Exception as e:
            self._log_event("email", "IMAP 센서", f"IMAP 연결 대기/오류: {str(e)[:40]}", "SENSOR_INFO")

        return results

    def _decode_mime_words(self, s: str) -> str:
        if not s:
            return ""
        decoded_fragments = decode_header(s)
        out = []
        for frag, enc in decoded_fragments:
            if isinstance(frag, bytes):
                try:
                    out.append(frag.decode(enc or "utf-8", errors="replace"))
                except Exception:
                    out.append(frag.decode("utf-8", errors="replace"))
            else:
                out.append(str(frag))
        return "".join(out)

    def _extract_email_body(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdispo = str(part.get("Content-Disposition"))
                if ctype == "text/plain" and "attachment" not in cdispo:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace").strip()
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace").strip()
        return ""

    # ------------------------------------------------------------------
    # 2. 아이폰/맥 문자(SMS/iMessage) DB 자동 센싱 (~/Library/Messages/chat.db)
    # ------------------------------------------------------------------
    def crawl_macos_messages_db(self, limit: int = 20) -> List[Dict[str, Any]]:
        db_path = os.path.expanduser("~/Library/Messages/chat.db")
        if not os.path.exists(db_path):
            return []

        results = []
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
            cursor = conn.cursor()
            query = """
                SELECT
                    m.ROWID,
                     COALESCE(h.id, '문자발신자') AS sender,
                    m.text,
                    datetime(m.date/1000000000 + strftime('%s', '2001-01-01'), 'unixepoch', 'localtime') AS msg_time
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.text IS NOT NULL AND length(trim(m.text)) > 1
                ORDER BY m.date DESC
                LIMIT ?
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            for rowid, sender, text, msg_time in rows:
                uid = f"imsg_{rowid}"
                if uid in self.seen_ids:
                    continue
                self.seen_ids.add(uid)
                self.stats["total_sensed"] += 1
                self.stats["sms_sensed"] += 1
                results.append({
                    "id": uid,
                    "source": "문자",
                    "channel": "sms",
                    "sender": str(sender),
                    "subject": None,
                    "content": str(text).strip(),
                    "timestamp": str(msg_time)[-8:-3] if msg_time else datetime.now().strftime("%H:%M"),
                })
            conn.close()
        except Exception:
            # 전체 디스크 접근 권한(Full Disk Access) 미부여 시 조용히 패스
            pass
        return results

    # ------------------------------------------------------------------
    # 3. 로컬 Apple Mail (~/Library/Mail/*.emlx) 실시간 자동 크롤러
    # ------------------------------------------------------------------
    def crawl_apple_mail_emlx(self, limit: int = 20) -> List[Dict[str, Any]]:
        mail_root = os.path.expanduser("~/Library/Mail")
        if not os.path.exists(mail_root):
            return []

        results = []
        try:
            emlx_files = glob.glob(os.path.join(mail_root, "**/*.emlx"), recursive=True)
            emlx_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            for fpath in emlx_files[:limit]:
                uid = f"emlx_{os.path.basename(fpath)}_{int(os.path.getmtime(fpath))}"
                if uid in self.seen_ids:
                    continue
                self.seen_ids.add(uid)
                try:
                    with open(fpath, "rb") as f:
                        raw_bytes = f.read()
                    nl_idx = raw_bytes.find(b"\n")
                    rfc_bytes = raw_bytes[nl_idx + 1:] if nl_idx != -1 else raw_bytes
                    msg = email.message_from_bytes(rfc_bytes)
                    subject = self._decode_mime_words(msg.get("Subject", "(제목 없음)")).strip()
                    sender = self._decode_mime_words(msg.get("From", "이메일 발신자")).strip()
                    body = self._extract_email_body(msg)
                    full_text = f"{subject}\n{body}".strip() if body else subject
                    if not full_text:
                        continue
                    self.stats["total_sensed"] += 1
                    self.stats["email_sensed"] += 1
                    mtime_str = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%m/%d %H:%M")
                    results.append({
                        "id": uid,
                        "source": "이메일",
                        "channel": "email",
                        "sender": sender[:45],
                        "subject": subject[:80],
                        "content": full_text[:500],
                        "timestamp": mtime_str,
                    })
                except Exception:
                    continue
        except Exception:
            pass
        return results

    # ------------------------------------------------------------------
    # 4. 카카오톡 대화 파일 / 알림 폴더 자동 크롤링
    # ------------------------------------------------------------------
    def crawl_watched_kakao_files(self, max_lines_per_file: int = 40) -> List[Dict[str, Any]]:
        results = []
        kakao_regex = re.compile(r"\[(.*?)\]\s*\[(오전|오후)\s*(\d{1,2}:\d{1,2})\]\s*(.*)")

        for folder in self.watch_dirs:
            if not os.path.exists(folder):
                continue
            pattern = os.path.join(folder, "*KakaoTalk*.txt")
            files = glob.glob(pattern) + glob.glob(os.path.join(folder, "*카카오톡*.txt"))
            for fpath in files:
                try:
                    mtime = int(os.path.getmtime(fpath))
                    file_key = f"kfile_{fpath}_{mtime}"
                    if file_key in self.seen_ids:
                        continue
                    self.seen_ids.add(file_key)

                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()[-max_lines_per_file:]

                    for idx, line in enumerate(lines):
                        m = kakao_regex.search(line.strip())
                        if m:
                            sender, ampm, t_str, body = m.group(1), m.group(2), m.group(3), m.group(4)
                            uid = f"{file_key}_{idx}"
                            self.stats["total_sensed"] += 1
                            self.stats["kakao_sensed"] += 1
                            results.append({
                                "id": uid,
                                "source": "카카오톡",
                                "channel": "kakao",
                                "sender": sender,
                                "subject": None,
                                "content": body.strip(),
                                "timestamp": f"{ampm} {t_str}",
                            })
                except Exception:
                    continue
        return results

    # ------------------------------------------------------------------
    # 5. 통합 자동 센싱 1회 실행
    # ------------------------------------------------------------------
    def sense_all_channels(self) -> List[Dict[str, Any]]:
        collected = []
        collected.extend(self.crawl_macos_messages_db())
        collected.extend(self.crawl_apple_mail_emlx())
        collected.extend(self.crawl_all_imap_accounts())
        if collected:
            self.recent_items = (collected + self.recent_items)[:100]
        self.stats["last_crawl_at"] = datetime.now().strftime("%H:%M:%S")
        return self.recent_items
