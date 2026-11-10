"""결과 폴더를 채우고 비교하는 도구. run.sh·collect.sh·compare.sh가 불러요(표준 라이브러리만 써요).

  python3 perf/lib/tools.py prom <결과 폴더> <시작 epoch> <끝 epoch>   서버 지표 → CSV·JSON
  python3 perf/lib/tools.py pgdiff <before.csv> <after.csv> <out.csv>   테스트 동안 쌓인 쿼리 시간
  python3 perf/lib/tools.py row <결과 폴더>                             문서 「결과 기록」 표의 한 줄
  python3 perf/lib/tools.py compare <전 폴더> <후 폴더>                 전후 비교 표(마크다운)
"""

import csv
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard import PANELS  # noqa: E402

PROM = "http://localhost:9090"
KST = timezone(timedelta(hours=9))
API = 'job="api",uri!~"/actuator.*"'
TYPES = ["lookup", "search", "judge"]
TYPE_KO = {"lookup": "조회", "search": "검색", "judge": "판정"}
STAGE_SECONDS = {"stress": 180, "breakpoint": 120}
# config.js의 p95 기준(초)
P95_LIMIT = {"lookup": 0.2, "search": 0.5, "judge": 1.0}


def prom(path, **params):
    url = f"{PROM}/api/v1/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        body = json.load(r)
    if body.get("status") != "success":
        raise RuntimeError(body)
    return body["data"]["result"]


def instant(query, at):
    return prom("query", query=query, time=at)


def scalar(query, at):
    res = instant(query, at)
    return float(res[0]["value"][1]) if res else None


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN → None


# ── prom: 서버 지표 내보내기 ─────────────────────────────────────────────


def export_prom(out, start, end):
    out = Path(out)
    w = f"{max(int(end - start), 60)}s"

    def by_uri(q):
        return {(r["metric"].get("method"), r["metric"].get("uri")): num(r["value"][1]) for r in instant(q, end)}

    bucket = f"increase(http_server_requests_seconds_bucket{{{API}}}[{w}])"
    p95 = by_uri(f"histogram_quantile(0.95, sum by (le, method, uri) ({bucket}))")
    p99 = by_uri(f"histogram_quantile(0.99, sum by (le, method, uri) ({bucket}))")
    count = by_uri(f"sum by (method, uri) (increase(http_server_requests_seconds_count{{{API}}}[{w}]))")
    total = by_uri(f"sum by (method, uri) (increase(http_server_requests_seconds_sum{{{API}}}[{w}]))")
    errors = by_uri(
        f'sum by (method, uri) (increase(http_server_requests_seconds_count{{{API},status=~"5.."}}[{w}]))'
    )

    rows = []
    for key, n in count.items():
        if not n:
            continue
        rows.append(
            {
                "method": key[0],
                "uri": key[1],
                "count": round(n),
                "avg_ms": ms(total.get(key, 0) / n),
                "p95_ms": ms(p95.get(key)),
                "p99_ms": ms(p99.get(key)),
                "errors_5xx": round(errors.get(key) or 0),
            }
        )
    rows.sort(key=lambda r: r["p95_ms"] or 0, reverse=True)
    write_csv(out / "server_by_uri.csv", rows, ["method", "uri", "count", "avg_ms", "p95_ms", "p99_ms", "errors_5xx"])

    sub = f"[{w}:15s]"
    cpu = '(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))'
    steal = 'avg(rate(node_cpu_seconds_total{mode="steal"}[1m]))'
    heap = (
        '(sum by (job) (jvm_memory_used_bytes{area="heap",job="api"})'
        ' / sum by (job) (jvm_memory_max_bytes{area="heap",job="api"} > 0))'
    )
    summary = {
        "window": w,
        "server_rps": num(scalar(f"sum(increase(http_server_requests_seconds_count{{{API}}}[{w}]))", end)),
        "server_p95_ms": ms(scalar(f"histogram_quantile(0.95, sum by (le) ({bucket}))", end)),
        "server_p99_ms": ms(scalar(f"histogram_quantile(0.99, sum by (le) ({bucket}))", end)),
        "server_5xx": num(
            scalar(f'sum(increase(http_server_requests_seconds_count{{{API},status=~"5.."}}[{w}]))', end)
        ),
        "ec2_cpu_avg": num(scalar(f"avg_over_time({cpu}{sub})", end)),
        "ec2_cpu_max": num(scalar(f"max_over_time({cpu}{sub})", end)),
        "ec2_steal_max": num(scalar(f"max_over_time({steal}{sub})", end)),
        "ec2_mem_available_min_bytes": num(scalar(f"min_over_time(node_memory_MemAvailable_bytes[{w}])", end)),
        "api_heap_max_ratio": num(scalar(f"max_over_time({heap}{sub})", end)),
        "api_heap_max_bytes": num(scalar('sum(jvm_memory_max_bytes{area="heap",job="api"} > 0)', end)),
        "api_gc_pause_max_ms": ms(scalar(f'max_over_time(max(jvm_gc_pause_seconds_max{{job="api"}})[{w}:5s])', end)),
        "hikari_max": num(scalar('sum(hikaricp_connections_max{job="api"})', end)),
        "hikari_active_max": num(scalar(f'max_over_time(sum(hikaricp_connections_active{{job="api"}})[{w}:5s])', end)),
        "hikari_pending_max": num(
            scalar(f'max_over_time(sum(hikaricp_connections_pending{{job="api"}})[{w}:5s])', end)
        ),
        "containers": {
            r["metric"].get("name"): {"mem_max_bytes": num(r["value"][1])}
            for r in instant(f'max_over_time(container_memory_working_set_bytes{{name=~"mujuthaek-.+"}}[{w}])', end)
        },
    }
    for r in instant(
        f'max_over_time(sum by (name) (rate(container_cpu_usage_seconds_total{{name=~"mujuthaek-.+"}}[1m])){sub})', end
    ):
        summary["containers"].setdefault(r["metric"].get("name"), {})["cpu_max_cores"] = num(r["value"][1])
    if summary["server_rps"] is not None:
        summary["server_rps"] = round(summary["server_rps"] / (end - start), 2)
    (out / "server_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    # 대시보드 패널과 같은 쿼리를 15초 간격 CSV로: 이미지 없이도 숫자로 다시 그릴 수 있어요
    ts = out / "timeseries"
    ts.mkdir(exist_ok=True)
    for i, (title, _unit, targets) in enumerate(PANELS, start=1):
        rows = []
        for expr, legend in targets:
            for r in prom("query_range", query=expr, start=start, end=end, step=15):
                label = legend
                for k, v in r["metric"].items():
                    label = label.replace("{{" + k + "}}", v)
                for t, v in r["values"]:
                    rows.append({"time": kst(float(t)), "series": label, "value": v})
        write_csv(ts / f"{i:02d}.csv", rows, ["time", "series", "value"], title)

    meta = json.loads((out / "meta.json").read_text()) if (out / "meta.json").exists() else {}
    if meta.get("test") in STAGE_SECONDS:
        export_stages(out, start, end, STAGE_SECONDS[meta["test"]])


def export_stages(out, start, end, step):
    """스트레스·한계 찾기: 단계(3분·2분)마다 RPS·에러율·p95를 한 줄씩. 기준을 처음 넘은 단계가 한계예요."""
    rows = []
    t = start + step
    while t <= end + 1:
        w = f"{step}s"
        row = {
            "stage_end": kst(t),
            "vus_max": num(scalar(f"max_over_time(sum(k6_vus)[{w}:5s])", t)),
            "rps": num(scalar(f"sum(increase(k6_http_reqs_total[{w}])) / {step}", t)),
            "error_rate": num(
                scalar(
                    f'sum(increase(k6_http_reqs_total{{expected_response="false"}}[{w}]))'
                    f" / sum(increase(k6_http_reqs_total[{w}]))",
                    t,
                )
            ),
            "server_p95_ms": ms(
                scalar(
                    f"histogram_quantile(0.95, sum by (le) (increase(http_server_requests_seconds_bucket{{{API}}}[{w}])))",
                    t,
                )
            ),
        }
        over = []
        for ty in TYPES:
            v = num(scalar(f'avg_over_time(max(k6_http_req_duration_p95{{type="{ty}"}})[{w}:5s])', t))
            row[f"k6_p95_{ty}_ms"] = ms(v)
            if v is not None and v > P95_LIMIT[ty]:
                over.append(TYPE_KO[ty])
        if (row["error_rate"] or 0) >= 0.01:
            over.append("에러율")
        row["over"] = "·".join(over)
        rows.append(row)
        t += step
    cols = ["stage_end", "vus_max", "rps", "error_rate", "k6_p95_lookup_ms", "k6_p95_search_ms", "k6_p95_judge_ms", "server_p95_ms", "over"]
    write_csv(Path(out) / "stages.csv", rows, cols)


# ── pgdiff ──────────────────────────────────────────────────────────────


def pgdiff(before, after, out):
    def load(p):
        with open(p, newline="") as f:
            return {r["queryid"]: r for r in csv.DictReader(f)}

    b, a = load(before), load(after)
    rows = []
    for qid, r in a.items():
        prev = b.get(qid, {})
        calls = int(r["calls"]) - int(prev.get("calls", 0))
        if calls <= 0:
            continue
        total = float(r["total_ms"]) - float(prev.get("total_ms", 0))
        rows.append(
            {
                "total_ms": round(total, 1),
                "calls": calls,
                "mean_ms": round(total / calls, 2),
                "rows": int(r["rows"]) - int(prev.get("rows", 0)),
                "blks_read": int(r["shared_blks_read"]) - int(prev.get("shared_blks_read", 0)),
                "queryid": qid,
                "query": r["query"],
            }
        )
    rows.sort(key=lambda r: r["total_ms"], reverse=True)
    write_csv(out, rows[:50], ["total_ms", "calls", "mean_ms", "rows", "blks_read", "queryid", "query"])


# ── row · compare ───────────────────────────────────────────────────────


def load_result(d):
    d = Path(d)
    meta = json.loads((d / "meta.json").read_text())
    k6 = json.loads((d / "summary.json").read_text()).get("metrics", {}) if (d / "summary.json").exists() else {}
    srv = json.loads((d / "server_summary.json").read_text()) if (d / "server_summary.json").exists() else {}
    uris = read_csv(d / "server_by_uri.csv")
    slow = read_csv(d / "slow_queries.csv")
    stages = read_csv(d / "stages.csv")
    return meta, k6, srv, uris, slow, stages


def k6v(k6, metric, stat):
    m = k6.get(metric)
    if not m:
        return None
    return (m.get("values") or m).get(stat)


def k6_type(k6, ty):
    key = f"http_req_duration{{type:{ty}}}"
    return k6v(k6, key, "p(95)"), k6v(k6, key, "p(99)")


def limit_stage(stages):
    for s in stages:
        if s.get("over"):
            return s
    return None


def row(d):
    meta, k6, srv, uris, _slow, stages = load_result(d)
    lat = " / ".join(f"{fmt(p95)}·{fmt(p99)}" for p95, p99 in (k6_type(k6, t) for t in TYPES))
    slowest = uris[0] if uris else None
    server = f"{slowest['p95_ms']}·{slowest['p99_ms']} ({slowest['method']} {slowest['uri']})" if slowest else "-"
    err = k6v(k6, "http_req_failed", "rate")
    bottleneck = ""
    lim = limit_stage(stages)
    if meta["test"] == "stress":
        bottleneck = f"한계 VU: {lim['vus_max'] if lim else '넘지 않음'}"
    elif meta["test"] == "breakpoint":
        prev = stages[stages.index(lim) - 1] if lim and stages.index(lim) > 0 else None
        bottleneck = f"최대 RPS: {prev['rps'] if prev else ('-' if lim else '넘지 않음')}"
    cells = [
        meta["started_at"][:16].replace("T", " "),
        TEST_KO.get(meta["test"], meta["test"]),
        meta.get("api_tag", "-"),
        meta.get("load", ""),
        fmt(k6v(k6, "http_reqs", "rate"), 1),
        lat,
        server,
        f"{err * 100:.2f}%" if err is not None else "-",
        bottleneck,
        meta.get("note", ""),
    ]
    print("| " + " | ".join(str(c) for c in cells) + " |")


TEST_KO = {"smoke": "스모크", "load": "부하", "soak": "내구", "stress": "스트레스", "breakpoint": "한계 찾기", "spike": "스파이크"}


def compare(da, db):
    ma, ka, sa, ua, qa, sta = load_result(da)
    mb, kb, sb, ub, qb, stb = load_result(db)
    print(f"## {TEST_KO.get(ma['test'], ma['test'])}: {ma.get('api_tag')} → {mb.get('api_tag')}\n")
    if mb.get("note"):
        print(f"고친 것: {mb['note']}\n")
    print("| 지표 | 전 | 후 | 변화 |\n|---|---|---|---|")
    lines = [("초당 요청(k6)", k6v(ka, "http_reqs", "rate"), k6v(kb, "http_reqs", "rate"), 1)]
    for t in TYPES:
        a95, a99 = k6_type(ka, t)
        b95, b99 = k6_type(kb, t)
        lines += [(f"k6 {TYPE_KO[t]} p95 (ms)", a95, b95, 0), (f"k6 {TYPE_KO[t]} p99 (ms)", a99, b99, 0)]
    lines += [
        ("에러율 (%)", pct(k6v(ka, "http_req_failed", "rate")), pct(k6v(kb, "http_req_failed", "rate")), 2),
        ("서버 p95 (ms)", sa.get("server_p95_ms"), sb.get("server_p95_ms"), 0),
        ("서버 p99 (ms)", sa.get("server_p99_ms"), sb.get("server_p99_ms"), 0),
        ("EC2 CPU 평균 (%)", pct(sa.get("ec2_cpu_avg")), pct(sb.get("ec2_cpu_avg")), 1),
        ("EC2 CPU 최대 (%)", pct(sa.get("ec2_cpu_max")), pct(sb.get("ec2_cpu_max")), 1),
        ("힙 최대 (%)", pct(sa.get("api_heap_max_ratio")), pct(sb.get("api_heap_max_ratio")), 1),
        ("GC 멈춤 최대 (ms)", sa.get("api_gc_pause_max_ms"), sb.get("api_gc_pause_max_ms"), 0),
        ("DB 커넥션 사용 최대", sa.get("hikari_active_max"), sb.get("hikari_active_max"), 0),
        ("DB 커넥션 대기 최대", sa.get("hikari_pending_max"), sb.get("hikari_pending_max"), 0),
    ]
    la, lb = limit_stage(sta), limit_stage(stb)
    if ma["test"] == "stress":
        lines.append(("한계 VU", num(la and la["vus_max"]), num(lb and lb["vus_max"]), 0))
    for name, a, b, nd in lines:
        print(f"| {name} | {fmt(a, nd)} | {fmt(b, nd)} | {change(a, b)} |")

    print("\n### API별 서버 p95 (전 기준 느린 10개)\n\n| API | 전 p95 | 후 p95 | 변화 |\n|---|---|---|---|")
    after = {(u["method"], u["uri"]): u for u in ub}
    for u in ua[:10]:
        v = after.get((u["method"], u["uri"]), {})
        print(f"| {u['method']} {u['uri']} | {u['p95_ms']} | {v.get('p95_ms', '-')} | {change(num(u['p95_ms']), num(v.get('p95_ms')))} |")

    print("\n### 느린 쿼리 (전 기준 총 시간 상위 5개)\n\n| 쿼리 | 전 평균 ms | 후 평균 ms | 전 호출 | 후 호출 |\n|---|---|---|---|---|")
    after_q = {q["queryid"]: q for q in qb}
    for q in qa[:5]:
        v = after_q.get(q["queryid"], {})
        text = q["query"][:80].replace("|", "\\|")
        print(f"| `{text}` | {q['mean_ms']} | {v.get('mean_ms', '-')} | {q['calls']} | {v.get('calls', '-')} |")


# ── 공통 ────────────────────────────────────────────────────────────────


def ms(v):
    v = num(v)
    return None if v is None else round(v * 1000, 1)


def pct(v):
    v = num(v)
    return None if v is None else v * 100


def fmt(v, nd=0):
    v = num(v)
    if v is None:
        return "-"
    return f"{v:.{nd}f}" if nd else f"{round(v)}"


def change(a, b):
    a, b = num(a), num(b)
    if a is None or b is None or a == 0:
        return "-"
    return f"{(b - a) / a * 100:+.0f}%"


def kst(epoch):
    return datetime.fromtimestamp(epoch, KST).isoformat(timespec="seconds")


def write_csv(path, rows, cols, title=None):
    with open(path, "w", newline="") as f:
        if title:
            f.write(f"# {title}\n")
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    if cmd == "prom":
        export_prom(args[0], float(args[1]), float(args[2]))
    elif cmd == "pgdiff":
        pgdiff(*args)
    elif cmd == "row":
        row(args[0])
    elif cmd == "compare":
        compare(args[0], args[1])
    else:
        print(__doc__)
        sys.exit(1)
