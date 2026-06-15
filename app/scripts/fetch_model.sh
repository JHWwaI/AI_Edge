#!/usr/bin/env bash
# YOLOv8n 사전학습 가중치를 ./models 로 받는다.
# ultralytics 공식 릴리스 v8.3.0 자산을 사용한다.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p models
URL="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt"
echo "downloading $URL -> models/yolov8n.pt"
curl -L -o models/yolov8n.pt "$URL"
ls -lh models/yolov8n.pt
