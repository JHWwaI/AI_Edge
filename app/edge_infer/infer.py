"""Edge inference worker.

YOLOv8n으로 비디오 프레임을 추론하고 conf>=CONF_TH 객체만
중앙 Postgres(detections 테이블)에 INSERT 한다.

환경변수:
  DEVICE_ID   엣지 노드 식별자 (예: edge-01)
  VIDEO_FILE  /videos 볼륨 기준 비디오 파일명
  MODEL_PATH  /models 볼륨 기준 가중치 경로 (기본 /models/yolov8n.pt)
  CONF_TH     confidence 임계값 (기본 0.6)
  DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
"""
import os
import time
import logging
from pathlib import Path

import cv2
import psycopg2
from psycopg2.extras import execute_values
from ultralytics import YOLO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("edge_infer")

DEVICE_ID = os.environ["DEVICE_ID"]
VIDEO_FILE = os.environ["VIDEO_FILE"]
MODEL_PATH = os.environ.get("MODEL_PATH", "/models/yolov8n.pt")
CONF_TH = float(os.environ.get("CONF_TH", "0.6"))
# N 프레임마다 1장만 추론 — 저사양 엣지에서 CPU/저장량을 줄이는 샘플링 간격.
FRAME_STRIDE = int(os.environ.get("FRAME_STRIDE", "5"))
# 추론 입력 해상도(px). 작을수록 빠르지만 작은 객체 검출률이 떨어진다.
IMG_SIZE = int(os.environ.get("IMG_SIZE", "480"))
LOOP = os.environ.get("LOOP", "false").lower() in ("1", "true", "yes")

DB_CFG = dict(
    host=os.environ.get("DB_HOST", "db"),
    port=int(os.environ.get("DB_PORT", "5432")),
    dbname=os.environ.get("DB_NAME", "edge"),
    user=os.environ.get("DB_USER", "edge"),
    password=os.environ.get("DB_PASSWORD", "edge"),
)


def connect_db_with_retry(max_wait_s: int = 60):
    """DB 연결을 최대 max_wait_s 초 동안 2초 간격으로 재시도한다.

    컨테이너 기동 순서상 db 가 아직 준비되지 않을 수 있어 재시도가 필요하다.
    성공 시 autocommit 커넥션을 반환하고, 기한 내 실패하면 RuntimeError 를 던진다.
    """
    deadline = time.time() + max_wait_s
    last_err = None
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(**DB_CFG)
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError as e:
            last_err = e
            log.info("DB not ready, retrying in 2s...")
            time.sleep(2)
    raise RuntimeError(f"DB connect failed: {last_err}")


def insert_detections(conn, rows):
    """detections 테이블에 검출 행들을 배치 INSERT 한다.

    각 row 는 아래 컬럼 순서의 튜플이어야 한다(execute_values 로 일괄 적재):
        (device_id, frame_idx, class_id, class_name, confidence,
         x1, y1, x2, y2, captured_at)
    rows 가 비어 있으면 아무 것도 하지 않는다.
    """
    if not rows:
        return
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO detections
                (device_id, frame_idx, class_id, class_name, confidence,
                 x1, y1, x2, y2, captured_at)
            VALUES %s
            """,
            rows,
        )


def main():
    """비디오를 FRAME_STRIDE 간격으로 추론해 검출을 중앙 DB로 적재하는 메인 루프.

    모델/영상 경로를 검증하고, DB 연결 후 프레임을 순회하며
    conf >= CONF_TH 객체만 detections 테이블에 INSERT 한다.
    LOOP=true 면 영상 끝에서 처음부터 다시 재생한다(엣지 카메라 스트림 모사).
    """
    video_path = Path("/videos") / VIDEO_FILE
    if not video_path.exists():
        raise FileNotFoundError(f"VIDEO_FILE not found: {video_path}")
    if not Path(MODEL_PATH).exists():
        raise FileNotFoundError(f"MODEL_PATH not found: {MODEL_PATH}")

    log.info("device=%s video=%s model=%s conf>=%.2f",
             DEVICE_ID, video_path, MODEL_PATH, CONF_TH)

    model = YOLO(MODEL_PATH)
    names = model.names
    conn = connect_db_with_retry()
    log.info("DB connected")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")

    frame_idx = 0
    kept_total = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                if LOOP:
                    # 영상 끝 → 처음부터 다시 (실 엣지 카메라 스트림 모사)
                    cap.release()
                    cap = cv2.VideoCapture(str(video_path))
                    log.info("loop: restarting video (frames so far=%d)", frame_idx)
                    continue
                break
            frame_idx += 1
            if frame_idx % FRAME_STRIDE != 0:
                continue

            results = model.predict(
                frame, conf=CONF_TH, verbose=False, imgsz=IMG_SIZE
            )[0]

            rows = []
            for box in results.boxes:
                conf = float(box.conf.item())
                if conf < CONF_TH:
                    continue
                cls_id = int(box.cls.item())
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                rows.append((
                    DEVICE_ID, frame_idx, cls_id, names.get(cls_id, str(cls_id)),
                    conf, x1, y1, x2, y2, time.strftime("%Y-%m-%d %H:%M:%S"),
                ))

            if rows:
                insert_detections(conn, rows)
                kept_total += len(rows)
                log.info("frame=%d kept=%d total=%d",
                         frame_idx, len(rows), kept_total)
    finally:
        cap.release()
        conn.close()
        log.info("done frames=%d kept=%d", frame_idx, kept_total)


if __name__ == "__main__":
    main()
