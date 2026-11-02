# 📱 JEV (Just Essential View) — Wirelog 뉴로-심볼릭 추론 기반 중요 문자·카카오톡·이메일 1줄 요약 비서

> **배포 도메인**: [`https://jevai.net/`](https://jevai.net/) | **웹 앱 데모**: [`https://kangsik-seo.github.io/jev/`](https://kangsik-seo.github.io/jev/)  
> **클라우드 인프라**: Google Cloud Platform (`asia-northeast3` 서울 리전 — Cloud Run / Cloud Storage / Compute Engine) & 온디바이스 오프라인 추론

---

## 📌 1. 프로젝트 개요

매일 쏟아지는 스팸 문자, 단체 카카오톡 잡담, 광고 이메일 속에서 **중요한 문자(SMS), 중요한 카카오톡 대화, 중요한 이메일**만 자동으로 선별(Triage)하여 **핵심 1줄 요약과 해야 할 일(Action Item)**을 도출해 주는 뉴로-심볼릭(Neuro-Symbolic) AI 요약 서비스입니다.

1. **오픈소스 [`wirelog`](https://github.com/semantic-reasoning/wirelog) Datalog 추론 엔진 결합**:
   - 비정형 한국어 메시지에서 추출한 기초 사실(EDB: 발신자, 시간·기한, 금액·결제, 인증번호, 배송, 업무 요청)을 입력받아 호른절(Horn Clause) 규칙(`.dl`)으로 중요도를 연역 추론(IDB)합니다.
   - LLM 단독 요약의 환각(Hallucination)을 방지하고, **왜 이 문자·카톡·이메일이 중요한지 점수와 추론 증명 트레이스(`Score & Proof Trace`)**를 투명하게 제시합니다.
2. **온디바이스 오프라인 구동 & Google Cloud 하이브리드 공유**:
   - 스마트폰·브라우저 내부 인메모리 엔진(`index.html`)과 로컬 SLM(`Qwen 2.5 1.5B`)으로 네트워크 없이도 민감한 개인 메시지를 안전하게 요약합니다.
   - 동시에 **Google Cloud Platform (Cloud Storage / Cloud Run / Compute Engine 서울 리전 `asia-northeast3`)** 배포 파이프라인을 통해 어디서든 웹·모바일 링크로 즉시 공유하고 접속할 수 있습니다.

---

## 🚀 2. 주요 구성 파일

| 파일 / 경로 | 설명 |
|---|---|
| [`index.html`](index.html) | **JEV × Wirelog 모바일/웹 1줄 요약 앱** (단일 HTML 오프라인/클라우드 호스팅용 PWA) |
| [`app.py`](app.py) | FastAPI 기반 웹 대시보드 및 REST API 서버 (`http://localhost:8000`) |
| [`cli.py`](cli.py) | 터미널 기반 중요 문자·카톡·이메일 브리핑 CLI |
| [`service.py`](service.py) / [`prompts.py`](prompts.py) | 온디바이스 SLM (`Qwen 2.5 1.5B`) 연동 및 규칙 기반 폴백 추론기 |
| [`sample_messages.json`](sample_messages.json) | 문자(KB국민카드, 쿠팡, 스팸), 카카오톡(팀장 업무요청, 단톡방, 가족), 이메일(AWS 장애, 계약서 검토) 샘플 |
| [`mobile/`](mobile/) | Android (`NotificationListenerService`) 및 iOS (`UNNotificationServiceExtension`) 실시간 수집 코드 |
| [`cloudbuild.yaml`](cloudbuild.yaml) / [`app.yaml`](app.yaml) | **Google Cloud Build / Cloud Run / App Engine** 자동 배포 명세 |
| [`scripts/deploy-gcp.sh`](scripts/deploy-gcp.sh) | **Google Cloud (`asia-northeast3`)** Cloud Storage & Cloud Run 원클릭 공유 스크립트 |

---

## ☁️ 3. Google Cloud 배포 및 공유 방법

```bash
# 1. Google Cloud 인증 및 배포 스크립트 실행 (서울 리전 asia-northeast3)
gcloud auth login
chmod +x scripts/deploy-gcp.sh
./scripts/deploy-gcp.sh
```

## 💻 4. 로컬 실행 방법

```bash
# 방법 1: 단일 HTML 모바일 웹앱 바로 열기 (인터넷 불필요)
open index.html

# 방법 2: FastAPI 웹 대시보드 실행
python3 app.py

# 방법 3: CLI 터미널 브리핑 실행
python3 cli.py
```
