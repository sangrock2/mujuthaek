"""이벤트를 저장소의 contracts/events/<eventType>.v<schemaVersion>.json 스키마로 검사해요.

테스트에서 씀: 이벤트를 만드는 쪽(collector)과 받는 쪽(extraction)이 같은 스키마로 확인해요.
jsonschema는 테스트(dev) 의존성이라 필요할 때만 불러와요.
스키마 폴더는 CONTRACTS_DIR 환경 변수로 바꿀 수 있고, 없으면 이 파일 위쪽 폴더에서 contracts/events를 찾아요.
extraction.completed처럼 다른 스키마 파일을 $id 주소(https://mujuthaek.kr/contracts/...)로 가리키는 이벤트가 있어서,
contracts/events·schemas의 스키마를 $id로 모아 둔 registry로 참조를 풀어요 (네트워크로 받지 않아요).
"""

import json
import os
from functools import cache
from pathlib import Path
from typing import Any


def events_dir() -> Path:
    if os.getenv("CONTRACTS_DIR"):
        return Path(os.environ["CONTRACTS_DIR"]) / "events"
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "events"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("contracts/events 폴더를 찾지 못했어요 (CONTRACTS_DIR로 지정할 수 있어요)")


@cache
def load_schema(event_type: str, version: int) -> dict[str, Any]:
    path = events_dir() / f"{event_type}.v{version}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def registry() -> Any:
    """contracts/events·schemas의 스키마를 $id로 모은 referencing.Registry. $id가 없는 스키마는 넣지 않아요."""
    from referencing import Registry, Resource

    root = events_dir().parent
    paths = [p for folder in ("events", "schemas") for p in sorted((root / folder).glob("*.json"))]
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    return Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas if "$id" in s)


def validate_event(event: dict[str, Any]) -> None:
    """스키마와 맞지 않으면 jsonschema.ValidationError를 내요."""
    from jsonschema import Draft202012Validator, FormatChecker

    schema = load_schema(event["eventType"], event["schemaVersion"])
    Draft202012Validator(schema, registry=registry(), format_checker=FormatChecker()).validate(event)
