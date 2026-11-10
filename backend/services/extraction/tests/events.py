"""테스트용 수집 이벤트(raw.notice.collected). 패키지 코드를 부르지 않아 입력 해석 테스트도 처리 흐름 없이 쓸 수 있습니다."""

from pathlib import Path

CONTRACTS = next(p for p in Path(__file__).resolve().parents if (p / "contracts" / "examples").is_dir()) / "contracts"
TEXT = (CONTRACTS / "examples" / "sources" / "housing.synthetic.txt").read_bytes().decode("utf-8")


def raw_event(**overrides):
    payload = {
        "rawPostId": "01929a3e-0000-7000-8000-000000000001",
        "version": 1,
        "sourceCode": "virtual",
        "provider": "가상주거공사",
        "regionCode": None,
        "field": "HOUSING",
        "kind": "NOTICE",
        "title": "가상주거 청년 매입임대 입주자 모집 공고",
        "postedOn": "2026-10-01",
        "detailUrl": None,
        "supersedesPostId": None,
        "text": TEXT,
        "textKey": None,
        "units": [],
        "files": [],
        "reprocess": False,
    } | overrides
    return {
        "eventId": "01929a3e-0000-7000-8000-0000000000e1",
        "eventType": "raw.notice.collected",
        "schemaVersion": 1,
        "occurredAt": "2026-10-15T00:00:00Z",
        "producer": "collector",
        "traceId": "trace-1",
        "payload": payload,
    }
