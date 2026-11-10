"""비교 B: 목록 API 읽기 — 공고 N개 + 항목 점수 5개 + 화면용 지표 4개."""

import os
import random
import statistics
import time

import psycopg

DSN = os.environ.get("BENCH_DSN", "host=localhost dbname=bench user=postgres password=test")
RTT_MS = 1.0
SHOW = ["station_nearest_m", "bus_stop_count_300m", "convenience_store_count_300m", "clinic_count_500m"]
PAGE = """select id, site_id, title, status, apply_end from bench.notices
          where status in ('UPCOMING','APPLYING') order by apply_end, id limit %(n)s offset %(off)s"""


def b1(cur, n, off):  # 조인 한 번
    cur.execute(
        f"""select p.*, sc.scores, mt.metrics from ({PAGE}) p
      left join lateral (select jsonb_object_agg(category, score) scores from bench.loc_scores where site_id = p.site_id) sc on true
      left join lateral (select jsonb_object_agg(metric, value) metrics from bench.loc_metrics
                         where site_id = p.site_id and metric = any(%(show)s)) mt on true
      order by p.apply_end, p.id""",
        {"n": n, "off": off, "show": SHOW},
    )
    cur.fetchall()
    return 1


def b2(cur, n, off):  # 나눠서 두 번
    cur.execute(PAGE, {"n": n, "off": off})
    rows = cur.fetchall()
    ids = [r[1] for r in rows]
    cur.execute(
        """select site_id, 'S', category, score::numeric from bench.loc_scores where site_id = any(%(ids)s)
                   union all
                   select site_id, 'M', metric, value from bench.loc_metrics where site_id = any(%(ids)s) and metric = any(%(show)s)""",
        {"ids": ids, "show": SHOW},
    )
    cur.fetchall()
    return 2


def b3(cur, n, off):  # 공고마다 (N+1)
    cur.execute(PAGE, {"n": n, "off": off})
    rows = cur.fetchall()
    q = 1
    for r in rows:
        cur.execute("select category, score from bench.loc_scores where site_id = %s", (r[1],))
        cur.fetchall()
        cur.execute("select metric, value from bench.loc_metrics where site_id = %s and metric = any(%s)", (r[1], SHOW))
        cur.fetchall()
        q += 2
    return q


with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
    for n in (20, 300):
        print(f"공고 {n}개씩 읽기 (300번 반복)")
        for name, fn in (("B1 조인 한 번", b1), ("B2 나눠서 두 번", b2), ("B3 공고마다(N+1)", b3)):
            random.seed(1)
            times = []
            q = 0
            for i in range(330):
                t = time.perf_counter()
                q = fn(cur, n, random.randint(0, 1200))
                el = (time.perf_counter() - t) * 1000
                if i >= 30:
                    times.append(el)
            times.sort()
            p50 = statistics.median(times)
            p95 = times[int(len(times) * 0.95)]
            print(
                f"  {name:<16} 중앙값 {p50:6.2f}ms  95% {p95:6.2f}ms  쿼리 {q:>3}번  왕복 1ms 가정 중앙값 {p50 + q * RTT_MS:6.1f}ms"
            )
