# AI_Edge — YOLOv8n 다중 엣지 추론 PoC

드론·차량 블랙박스 등 엣지 디바이스에서 들어오는 영상을 **YOLOv8n** 으로
실시간 탐지하고, **confidence ≥ 0.6** 결과만 중앙 PostgreSQL에 적재하는
**다중 엣지 노드 시뮬레이션** 입니다. ADAS 블랙박스 영상 인식·NPU 배포
직무의 문제 구조(저사양 노드 × 동일 이미지 다중 배포 × 중앙 집계)와
동일한 형태로 만들었습니다.

## 구성 요소

```
AI_Edge/
├── edge_infer/        # YOLOv8n 추론 컨테이너 (동일 이미지를 N개 노드로 배포)
│   ├── infer.py
│   ├── requirements.txt
│   └── Dockerfile
├── monitor/           # DB 1초 폴링 모니터 (데이터 흐름 실시간 검증)
│   ├── monitor.py
│   ├── requirements.txt
│   └── Dockerfile
├── db/
│   └── init.sql       # detections 테이블 스키마
├── models/            # 모델 가중치 (별도 볼륨 — 모델 버전만 독립 교체)
├── videos/            # 영상 데이터 (별도 볼륨)
├── scripts/
│   ├── fetch_model.sh
│   └── fetch_sample_video.sh
├── docker-compose.yml # CPU 0.5 / Mem 512M 제한 + 다중 엣지 노드
└── .env.example
```

## 설계 포인트

| 이력서 항목 | 구현 위치 |
| --- | --- |
| YOLOv8n 실시간 탐지 → 중앙 DB 적재 | `edge_infer/infer.py`, `db/init.sql` |
| confidence ≥ 0.6 만 INSERT (저장량 폭주 방지) | `infer.py` 의 `CONF_TH` 필터 |
| CPU 0.5 코어 / Mem 512M 리소스 제한 | `docker-compose.yml` 의 `cpus`/`mem_limit` |
| `DEVICE_ID`/`VIDEO_FILE` 환경변수 주입 → 동일 이미지 다중 배포 | `edge-01/02/03` 서비스의 `environment` |
| 모델 가중치를 별도 볼륨으로 분리 (영상/모델 독립 교체) | `./models:/models:ro`, `./videos:/videos:ro` |
| DB 1초 폴링 모니터로 데이터 흐름 검증 | `monitor/monitor.py` |

## 실행

```bash
# 1) 모델 가중치 + 데모 영상 받기
bash scripts/fetch_model.sh
bash scripts/fetch_sample_video.sh

# 2) (선택) 노드별 영상 분리 + DB 비밀번호 — 같은 이미지에 다른 입력만 주입
cp .env.example .env

# 3) 클러스터 기동
docker compose up --build
```

기동 후 **http://localhost:8080** 대시보드에서 노드별 검출 수·분당 추이·
최근 검출이 2초마다 갱신되고, `monitor` 서비스 로그에서 1초마다 device_id 별
INSERT 건수·최근 클래스 Top-3·마지막 INSERT 시각이 갱신되는 것을 확인할 수 있습니다.

### DB 비밀번호

`docker-compose.yml` 은 비밀번호를 `${DB_PASSWORD:-edge}` 로 참조합니다.
`.env` 가 없으면 기본값 `edge` 로 동작하고, 운영 시 `.env` 에 `DB_PASSWORD=강한값`
을 지정하면 모든 서비스(db/edge/monitor/dashboard)에 일관되게 적용됩니다.

## 트러블슈팅

- **엣지 컨테이너가 바로 종료** → `docker compose logs edge-01` 로 영상/모델 경로·DB 연결 확인.
- **대시보드가 비어 있음** → `monitor` 로그에 INSERT 가 찍히는지 확인. 안 찍히면 엣지 측 문제.
- **`sample.mp4 not found`** → `bash scripts/fetch_sample_video.sh` 로 영상부터 받기.

## 동일 이미지 × 다중 노드 검증

`edge-01/02/03` 은 모두 같은 `ai-edge/infer:latest` 이미지를 사용하며,
다른 점은 다음 두 환경변수뿐입니다.

- `DEVICE_ID` — DB row의 식별자
- `VIDEO_FILE` — `/videos` 볼륨에서 읽을 파일명

엣지 노드 수를 늘리려면 `docker-compose.yml` 에 `edge-04`, `edge-05` …
블록을 같은 패턴으로 복제하면 됩니다.

## 한계 및 다음 단계

- 현재 입력은 파일 비디오 — 실 엣지 환경에서는 RTSP/USB 카메라 소스로 교체.
- INT8 양자화 후 NPU(예: Hailo-8, Ambarella CV2x) 배포 단계는 별도 트랙.
- 다중 노드 메트릭(FPS, latency)을 Prometheus + Grafana 로 시각화 예정.
