"""DB 1초 폴링 모니터.

device_id별 최근 1분간 INSERT 건수, 마지막 INSERT 시각,
가장 많이 탐지된 클래스 Top-3를 1초마다 출력한다.
"""
import os
import time
import psycopg2

DB_CFG = dict(
    host=os.environ.get("DB_HOST", "db"),  # compose 서비스명 기본값(타 서비스와 일치)
    port=int(os.environ.get("DB_PORT", "5432")),
    dbname=os.environ.get("DB_NAME", "edge"),
    user=os.environ.get("DB_USER", "edge"),
    password=os.environ.get("DB_PASSWORD", "edge"),
)


SUMMARY_SQL = """
SELECT device_id,
       COUNT(*)                                       AS last_1m,
       MAX(inserted_at)                               AS last_seen,
       MAX(confidence)                                AS max_conf
FROM detections
WHERE inserted_at > NOW() - INTERVAL '1 minute'
GROUP BY device_id
ORDER BY device_id;
"""

TOP_CLS_SQL = """
SELECT device_id, class_name, COUNT(*) AS n
FROM detections
WHERE inserted_at > NOW() - INTERVAL '1 minute'
GROUP BY device_id, class_name
ORDER BY device_id, n DESC;
"""


def connect_with_retry():
    """DB 가 준비될 때까지 2초 간격으로 재시도하며 autocommit 커넥션을 반환한다."""
    while True:
        try:
            c = psycopg2.connect(**DB_CFG)
            c.autocommit = True
            return c
        except psycopg2.OperationalError:
            print("[monitor] DB not ready, retry 2s")
            time.sleep(2)


def main():
    """1초마다 DB를 폴링해 device_id별 집계를 콘솔에 출력한다(에러 시 재연결)."""
    conn = connect_with_retry()
    print("[monitor] connected, polling every 1s (Ctrl-C to stop)")
    while True:
        try:
            with conn.cursor() as cur:
                cur.execute(SUMMARY_SQL)
                summary = cur.fetchall()
                cur.execute(TOP_CLS_SQL)
                cls_rows = cur.fetchall()

            top = {}
            for dev, name, n in cls_rows:
                top.setdefault(dev, []).append((name, n))

            ts = time.strftime("%H:%M:%S")
            if not summary:
                print(f"[{ts}] no detections in last 1 min")
            else:
                print(f"[{ts}] {'device':<10} {'last_1m':>8} {'last_seen':<20} top_classes")
                for dev, n1m, last_seen, max_conf in summary:
                    top3 = ", ".join(f"{c}:{k}" for c, k in top.get(dev, [])[:3])
                    print(f"           {dev:<10} {n1m:>8} {str(last_seen):<20} {top3}")
            time.sleep(1)
        except psycopg2.Error as e:
            print(f"[monitor] db error: {e}; reconnecting")
            try:
                conn.close()
            except Exception:
                pass
            conn = connect_with_retry()


if __name__ == "__main__":
    main()
