CREATE TABLE IF NOT EXISTS detections (
    id           BIGSERIAL PRIMARY KEY,
    device_id    TEXT        NOT NULL,
    frame_idx    INTEGER     NOT NULL,
    class_id     INTEGER     NOT NULL,
    class_name   TEXT        NOT NULL,
    confidence   REAL        NOT NULL,
    x1           REAL        NOT NULL,
    y1           REAL        NOT NULL,
    x2           REAL        NOT NULL,
    y2           REAL        NOT NULL,
    captured_at  TIMESTAMP   NOT NULL,
    inserted_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_detections_device_time
    ON detections (device_id, inserted_at DESC);
