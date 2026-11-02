#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-ks-work-7788}"
REGION="${GCP_REGION:-asia-northeast3}"
BUCKET_NAME="${PROJECT_ID}-jev-summarizer"
SERVICE_NAME="jev-summarizer"

echo "=== [1/3] Google Cloud 프로젝트 및 서울 리전(${REGION}) 설정 ==="
gcloud config set project "${PROJECT_ID}"
gcloud config set compute/region "${REGION}"

echo "=== [2/3] Google Cloud Storage 정적 모바일 웹앱(PWA) 공유 버킷 배포 ==="
gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET_NAME}" 2>/dev/null || true
gsutil iam ch allUsers:objectViewer "gs://${BUCKET_NAME}"
gsutil web set -m index.html -e index.html "gs://${BUCKET_NAME}"
gsutil -h "Content-Type:text/html; charset=utf-8" \
       -h "Cache-Control:public, max-age=300" \
       cp index.html "gs://${BUCKET_NAME}/index.html"
echo "✅ GCS 공유 URL: https://storage.googleapis.com/${BUCKET_NAME}/index.html"

echo "=== [3/3] Google Cloud Run 서버리스 요약 API & 대시보드 배포 ==="
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8000

echo "✅ Google Cloud 배포 완료!"
