import os
import random
import statistics
import time

import psycopg

DSN = os.environ.get("BENCH_DSN", "host=localhost dbname=bench user=postgres password=test")
Q = {
    "store_count_300m": "select count(*) from {t} s where st_dwithin(s.geom, {p}, 300)",
    "convenience_store_count_300m": "select count(*) from {t} s where s.industry_group='CONVENIENCE_STORE' and st_dwithin(s.geom, {p}, 300)",
    "mart_nearest_m": "select st_distance(s.geom, {p}) from {t} s where s.industry_group='MART' order by s.geom <-> {p} limit 1",
}
with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
    cur.execute("select st_astext(geom::geometry) from bench.sites")
    pts = [f"SRID=4326;{g}" for (g,) in cur.fetchall()]
    random.seed(3)
    sample = random.sample(pts, 300)
    for t in ("area.stores", "area.stores_part"):
        cols = ", ".join(f"({q.format(t=t, p='x.geom')}) as {k}" for k, q in Q.items())
        runs = []
        for _ in range(3):
            s = time.perf_counter()
            cur.execute(
                f"select sum(store_count_300m) + sum(convenience_store_count_300m) + sum(coalesce(mart_nearest_m, 0)) from (select x.id, {cols} from bench.sites x) z"
            )
            cur.fetchone()
            runs.append(time.perf_counter() - s)
        single = []
        sql = "select " + ", ".join(f"({q.format(t=t, p='%(g)s::geography')})" for q in Q.values())
        for i, g in enumerate(sample):
            s = time.perf_counter()
            cur.execute(sql, {"g": g})
            cur.fetchone()
            el = (time.perf_counter() - s) * 1000
            if i >= 20:
                single.append(el)
        single.sort()
        print(
            f"  {t:<17} 전체 3,000곳 한 쿼리 {statistics.median(runs):5.2f}초 | 단지 하나 중앙값 {statistics.median(single):5.2f}ms, 95% {single[int(len(single) * 0.95)]:5.2f}ms"
        )
