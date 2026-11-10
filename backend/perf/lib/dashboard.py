"""grafana/dashboards/perf.json을 만들어요. 패널을 고치면 이 파일을 고치고 `python3 perf/lib/dashboard.py`로 다시 써요.

패널 id는 run.sh가 이미지로 받을 때 쓰니 바꾸지 않아요(PANELS 순서 = id).
"""

import json
from pathlib import Path

UID = "mujuthaek-perf"
API = 'job="api",uri!~"/actuator.*"'
APP = 'name=~"mujuthaek-.+"'

# (제목, 단위, [(쿼리, 범례)])
PANELS = [
    ("k6 응답 시간 p95 (종류별)", "s", [('max by (type) (k6_http_req_duration_p95)', "{{type}}")]),
    ("k6 응답 시간 p99 (종류별)", "s", [('max by (type) (k6_http_req_duration_p99)', "{{type}}")]),
    ("k6 초당 요청 · 동시 사용자", "short", [
        ("sum(rate(k6_http_reqs_total[30s]))", "RPS"),
        ("sum(k6_vus)", "VU"),
    ]),
    ("k6 에러율", "percentunit", [(
        'sum(rate(k6_http_reqs_total{expected_response="false"}[30s])) / sum(rate(k6_http_reqs_total[30s]))', "에러율")]),
    ("서버 p95 (API별)", "s", [(
        f"histogram_quantile(0.95, sum by (le, method, uri) (rate(http_server_requests_seconds_bucket{{{API}}}[1m])))",
        "{{method}} {{uri}}")]),
    ("서버 p99 (API별)", "s", [(
        f"histogram_quantile(0.99, sum by (le, method, uri) (rate(http_server_requests_seconds_bucket{{{API}}}[1m])))",
        "{{method}} {{uri}}")]),
    ("서버 초당 요청 (상태별)", "reqps", [(
        f"sum by (status) (rate(http_server_requests_seconds_count{{{API}}}[1m]))", "{{status}}")]),
    ("EC2 CPU · steal(크레딧 바닥)", "percentunit", [
        ('1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))', "CPU 사용"),
        ('avg(rate(node_cpu_seconds_total{mode="steal"}[1m]))', "steal"),
    ]),
    ("컨테이너 CPU (코어)", "short", [(
        f"sum by (name) (rate(container_cpu_usage_seconds_total{{{APP}}}[1m]))", "{{name}}")]),
    ("컨테이너 메모리", "bytes", [(f"container_memory_working_set_bytes{{{APP}}}", "{{name}}")]),
    ("JVM 힙 사용률", "percentunit", [(
        'sum by (job) (jvm_memory_used_bytes{area="heap"}) / sum by (job) (jvm_memory_max_bytes{area="heap"} > 0)',
        "{{job}}")]),
    ("GC 멈춤 (초당 GC 시간 · 최대 한 번)", "s", [
        ("sum by (job) (rate(jvm_gc_pause_seconds_sum[1m]))", "{{job}} 초당"),
        ("max by (job) (jvm_gc_pause_seconds_max)", "{{job}} 최대"),
    ]),
    ("DB 커넥션 (Hikari)", "short", [
        ('sum(hikaricp_connections_active{job="api"})', "사용 중"),
        ('sum(hikaricp_connections_pending{job="api"})', "대기"),
        ('sum(hikaricp_connections_max{job="api"})', "최대"),
    ]),
    ("DB 커넥션 얻는 데 걸린 시간", "s", [(
        'rate(hikaricp_connections_acquire_seconds_sum{job="api"}[1m]) / rate(hikaricp_connections_acquire_seconds_count{job="api"}[1m])',
        "평균")]),
    ("EC2 남은 메모리", "bytes", [("node_memory_MemAvailable_bytes", "MemAvailable")]),
]


def panel(i, title, unit, targets):
    return {
        "id": i,
        "type": "timeseries",
        "title": title,
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": 0 if i % 2 else 12, "y": (i - 1) // 2 * 8},
        "fieldConfig": {"defaults": {"unit": unit, "custom": {"lineWidth": 1, "fillOpacity": 5}}, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
        "targets": [
            {"refId": chr(65 + n), "expr": expr, "legendFormat": legend, "datasource": {"type": "prometheus", "uid": "prometheus"}}
            for n, (expr, legend) in enumerate(targets)
        ],
    }


def dashboard():
    return {
        "uid": UID,
        "title": "무주택자들 성능 테스트",
        "timezone": "Asia/Seoul",
        "refresh": "5s",
        "time": {"from": "now-30m", "to": "now"},
        "schemaVersion": 39,
        "panels": [panel(i, *p) for i, p in enumerate(PANELS, start=1)],
    }


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "grafana/dashboards/perf.json"
    out.write_text(json.dumps(dashboard(), ensure_ascii=False, indent=2) + "\n")
    print(out)
