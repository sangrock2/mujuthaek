"""분야별 추출 규칙. 하위 폴더 하나가 분야 하나입니다(housing_notice, business_space, policy, startup_support).

자동 등록(요구 2-02, 2026-10-23): 폴더의 __init__.py가 FIELD(수집 이벤트의 field 값, 예: "HOUSING")와 RULES(FieldRules)를 내놓으면
pipeline이 그 분야를 처리합니다. 새 분야는 폴더(프롬프트·호출 목록·출력 한도)만 추가하면 되고 pipeline.py는 고치지 않습니다.
RULES_LEGACY가 있으면 이전 방식(EXTRACTION_METHOD=legacy)에도 씁니다(지금은 주거 v10만).
FIELD·RULES가 없는 폴더(아직 규칙이 없는 business_space·startup_support, 판정 틀 전용 읽기인 policy)는 건너뜁니다.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from mujuthaek_extraction.rules.base import FieldRules


def discover(package: ModuleType | None = None) -> tuple[dict[str, FieldRules], dict[str, FieldRules]]:
    """package(기본: 이 rules 패키지)의 하위 폴더에서 규칙을 모아 (구조 방식, 이전 방식) 분야별 규칙을 돌려줍니다.
    같은 FIELD를 두 폴더가 내놓으면 어느 규칙을 쓸지 모르므로 시작할 때 막습니다."""
    package = package or importlib.import_module(__name__)
    current: dict[str, FieldRules] = {}
    legacy: dict[str, FieldRules] = {}
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda i: i.name):
        if not info.ispkg:  # base.py 같은 파일은 분야가 아닙니다
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        field, rules = getattr(module, "FIELD", None), getattr(module, "RULES", None)
        if not isinstance(field, str) or not isinstance(rules, FieldRules):
            continue
        if field in current:
            raise ValueError(f"{field} 분야 규칙이 두 폴더에 있습니다({info.name}).")
        current[field] = rules
        if isinstance(old := getattr(module, "RULES_LEGACY", None), FieldRules):
            legacy[field] = old
    return current, legacy
