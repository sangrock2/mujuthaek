"""PostgreSQL 연결 (psycopg 3). 주소 예: postgresql://collector_app:collector-pass@localhost:5432/collector

연결은 기본으로 트랜잭션 안에서 시작해요. 문장마다 바로 반영하려면 conn.autocommit = True로 두고,
여러 문장을 묶을 때 `with conn.transaction():`을 써요.
"""

import psycopg


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, application_name="mujuthaek")
