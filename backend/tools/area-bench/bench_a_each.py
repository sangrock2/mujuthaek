import random
import time

import psycopg
from bench_a import DSN, METRICS, PT

with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
    cur.execute("select st_astext(geom::geometry) from bench.sites order by id")
    sites = [f"SRID=4326;{g}" for (g,) in cur.fetchall()]
    random.seed(7)
    sample = random.sample(sites, 200)
    res = []
    for k, q in METRICS.items():
        sql = q.format(p=PT)
        t = time.perf_counter()
        for g in sample:
            cur.execute(sql, {"geom": g})
            cur.fetchone()
        res.append((k, (time.perf_counter() - t) / len(sample) * 1000))
    for k, ms in sorted(res, key=lambda x: -x[1]):
        print(f"  {k:<30} 단지당 {ms:6.2f}ms")
    print(f"  합계 단지당 {sum(ms for _, ms in res):.1f}ms")
