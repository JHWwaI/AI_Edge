"""AI_Edge 실시간 대시보드 — FastAPI 백엔드.

엣지 노드(edge-01/02/03)가 Postgres에 적재한 detections 테이블을
주기적으로 폴링해 노드별 집계·최근 검출·시계열을 제공한다.

엔드포인트:
    GET /                  단일 페이지 대시보드 HTML
    GET /api/stats         노드별 집계 (총 건수, 최근 1분, 마지막 시각, top 클래스)
    GET /api/recent        최근 검출 N건 (기본 30)
    GET /api/timeline      최근 N분 시계열 (기본 5분, 분 단위)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DB_CFG = dict(
    host=os.environ.get("DB_HOST", "db"),
    port=int(os.environ.get("DB_PORT", "5432")),
    dbname=os.environ.get("DB_NAME", "edge"),
    user=os.environ.get("DB_USER", "edge"),
    password=os.environ.get("DB_PASSWORD", "edge"),
)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="AI_Edge Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@contextmanager
def get_conn():
    """autocommit Postgres 커넥션을 컨텍스트로 열고 종료 시 닫는다."""
    conn = psycopg2.connect(**DB_CFG)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


@app.get("/")
def index() -> FileResponse:
    """단일 페이지 대시보드 HTML 을 반환한다."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/stats")
def stats() -> dict:
    """노드별 집계: 총 건수, 최근 1분, 마지막 시각, top 클래스 3개."""
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT device_id,
                   COUNT(*)                                          AS total,
                   COUNT(*) FILTER (WHERE inserted_at > NOW() - INTERVAL '1 minute') AS last_1m,
                   MAX(inserted_at)                                  AS last_seen,
                   MAX(confidence)                                   AS max_conf,
                   AVG(confidence)                                   AS avg_conf
            FROM detections
            GROUP BY device_id
            ORDER BY device_id;
        """)
        summary = cur.fetchall()

        cur.execute("""
            SELECT device_id, class_name, COUNT(*) AS n
            FROM detections
            WHERE inserted_at > NOW() - INTERVAL '5 minute'
            GROUP BY device_id, class_name
            ORDER BY device_id, n DESC;
        """)
        cls_rows = cur.fetchall()

    top: dict[str, list[dict]] = {}
    for r in cls_rows:
        top.setdefault(r["device_id"], []).append(
            {"class": r["class_name"], "n": r["n"]}
        )

    return {
        "devices": [
            {
                "device_id": s["device_id"],
                "total": s["total"],
                "last_1m": s["last_1m"],
                "last_seen": s["last_seen"].isoformat() if s["last_seen"] else None,
                "max_conf": float(s["max_conf"]) if s["max_conf"] is not None else None,
                "avg_conf": float(s["avg_conf"]) if s["avg_conf"] is not None else None,
                "top_classes": top.get(s["device_id"], [])[:5],
            }
            for s in summary
        ]
    }


@app.get("/api/recent")
def recent(limit: int = Query(30, ge=1, le=200)) -> dict:
    """최근 검출 N건."""
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, device_id, frame_idx, class_name, confidence,
                   x1, y1, x2, y2, inserted_at
            FROM detections
            ORDER BY id DESC
            LIMIT %s;
        """, (limit,))
        rows = cur.fetchall()

    return {
        "rows": [
            {
                "id": r["id"],
                "device_id": r["device_id"],
                "frame_idx": r["frame_idx"],
                "class_name": r["class_name"],
                "confidence": float(r["confidence"]),
                "bbox": [float(r["x1"]), float(r["y1"]),
                         float(r["x2"]), float(r["y2"])],
                "inserted_at": r["inserted_at"].isoformat(),
            }
            for r in rows
        ]
    }


@app.get("/api/timeline")
def timeline(minutes: int = Query(5, ge=1, le=60)) -> dict:
    """노드별 분 단위 검출 건수 시계열."""
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT device_id,
                   date_trunc('minute', inserted_at) AS bucket,
                   COUNT(*) AS n
            FROM detections
            WHERE inserted_at > NOW() - (%s || ' minute')::interval
            GROUP BY device_id, bucket
            ORDER BY bucket, device_id;
        """, (str(minutes),))
        rows = cur.fetchall()

    series: dict[str, list[dict]] = {}
    for r in rows:
        series.setdefault(r["device_id"], []).append({
            "t": r["bucket"].isoformat(),
            "n": r["n"],
        })
    return {"series": series, "minutes": minutes}


@app.get("/api/health")
def health() -> dict:
    """DB 연결 상태를 점검해 ok/degraded 를 반환하는 헬스체크."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "degraded", "db": str(e)}
