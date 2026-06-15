#!/usr/bin/env bash
# 데모용 차량 주행 영상을 ./videos/sample.mp4 로 받는다.
# 공개 도메인(coverr.co 등) 영상을 사용하거나 직접 클립을 넣어도 된다.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p videos
if [ -f videos/sample.mp4 ]; then
  echo "videos/sample.mp4 already exists"
  exit 0
fi
URL="${SAMPLE_URL:-https://download.samplelib.com/mp4/sample-30s.mp4}"
echo "downloading $URL -> videos/sample.mp4"
curl -L -o videos/sample.mp4 "$URL"
ls -lh videos/sample.mp4
