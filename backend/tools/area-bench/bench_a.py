"""비교 A: 세권 지표 14개를 계산하는 세 가지 방식.

A1 지표마다 따로: 단지 하나에 쿼리 14번
A2 단지마다 한 쿼리: 단지 하나에 쿼리 1번 (스칼라 하위 쿼리 14개)
A3 전체 한 쿼리: 단지 3,000곳을 쿼리 1번으로 (집합 처리)
A1·A2는 단지 300곳으로 재고 3,000곳으로 환산해요.
"""

import os
import random
import sys
import time

import psycopg

DSN = os.environ.get("BENCH_DSN", "host=localhost dbname=bench user=postgres password=test")
SAMPLE = 300
RTT_MS = 1.0  # RDS 같은 영역 왕복 시간 가정

PT = "%(geom)s::geography"
METRICS = {
    "station_nearest_m": "select st_distance(f.geom, {p}) from area.facilities f where f.kind='SUBWAY_STATION' order by f.geom <-> {p} limit 1",
    "station_count_1km": "select count(*) from area.facilities f where f.kind='SUBWAY_STATION' and st_dwithin(f.geom, {p}, 1000)",
    "bus_stop_nearest_m": "select st_distance(f.geom, {p}) from area.facilities f where f.kind='BUS_STOP' order by f.geom <-> {p} limit 1",
    "bus_stop_count_300m": "select count(*) from area.facilities f where f.kind='BUS_STOP' and st_dwithin(f.geom, {p}, 300)",
    "elementary_nearest_m": "select st_distance(f.geom, {p}) from area.facilities f where f.kind='SCHOOL' and f.sub_kind='ELEMENTARY' order by f.geom <-> {p} limit 1",
    "middle_count_1km": "select count(*) from area.facilities f where f.kind='SCHOOL' and f.sub_kind='MIDDLE' and st_dwithin(f.geom, {p}, 1000)",
    "high_count_1km": "select count(*) from area.facilities f where f.kind='SCHOOL' and f.sub_kind='HIGH' and st_dwithin(f.geom, {p}, 1000)",
    "park_nearest_m": "select st_distance(f.geom, {p}) from area.facilities f where f.kind='PARK' order by f.geom <-> {p} limit 1",
    "park_area_1km_m2": "select coalesce(sum((f.extra->>'area_m2')::numeric), 0) from area.facilities f where f.kind='PARK' and st_dwithin(f.geom, {p}, 1000)",
    "hospital_nearest_m": "select st_distance(f.geom, {p}) from area.facilities f where f.kind='HOSPITAL' and f.sub_kind='SECONDARY' order by f.geom <-> {p} limit 1",
    "clinic_count_500m": "select count(*) from area.facilities f where f.kind='HOSPITAL' and f.sub_kind='CLINIC' and st_dwithin(f.geom, {p}, 500)",
    "convenience_store_count_300m": "select count(*) from area.stores s where s.industry_group='CONVENIENCE_STORE' and st_dwithin(s.geom, {p}, 300)",
    "mart_nearest_m": "select st_distance(s.geom, {p}) from area.stores s where s.industry_group='MART' order by s.geom <-> {p} limit 1",
    "store_count_300m": "select count(*) from area.stores s where st_dwithin(s.geom, {p}, 300)",
}


def a1(conn, sites):
    with conn.cursor() as cur:
        t = time.perf_counter()
        for _, geom in sites:
            for q in METRICS.values():
                cur.execute(q.format(p=PT), {"geom": geom})
                cur.fetchone()
        return time.perf_counter() - t, len(sites) * len(METRICS)


def a2(conn, sites):
    sql = "select " + ", ".join(f"({q.format(p=PT)}) as {k}" for k, q in METRICS.items())
    with conn.cursor() as cur:
        t = time.perf_counter()
        for _, geom in sites:
            cur.execute(sql, {"geom": geom})
            cur.fetchone()
        return time.perf_counter() - t, len(sites)


def a3(conn):
    cols = ", ".join(f"({q.format(p='t.geom')}) as {k}" for k, q in METRICS.items())
    sql = f"create temp table m as select t.id, {cols} from bench.sites t"
    with conn.cursor() as cur:
        cur.execute("drop table if exists m")
        t = time.perf_counter()
        cur.execute(sql)
        el = time.perf_counter() - t
        cur.execute("select count(*) from m")
        n = cur.fetchone()[0]
        return el, 1, n


def main(label):
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("select id, st_astext(geom::geometry) from bench.sites order by id")
            sites_all = cur.fetchall()
        random.seed(7)
        sample = [(i, f"SRID=4326;{g}") for i, g in random.sample(sites_all, SAMPLE)]
        a1(conn, sample[:20])  # 데우기
        el1, q1 = a1(conn, sample)
        el2, q2 = a2(conn, sample)
        el3, q3, _n = a3(conn)
        scale = len(sites_all) / SAMPLE
        rows = [
            ("A1 지표마다 따로", el1 * scale, q1 * scale),
            ("A2 단지마다 한 쿼리", el2 * scale, q2 * scale),
            ("A3 전체 한 쿼리", el3, q3),
        ]
        print(f"[{label}] 단지 {len(sites_all)}곳, 지표 {len(METRICS)}개 (A1·A2는 {SAMPLE}곳으로 재서 환산)")
        for name, sec, queries in rows:
            print(
                f"  {name:<14} DB {sec:7.1f}초  쿼리 {int(queries):>6}번  왕복 1ms 가정 {sec + queries * RTT_MS / 1000:7.1f}초"
            )
        return rows


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "기본")
