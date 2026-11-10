"""저장소의 contracts/ 검사기를 그대로 불러 씁니다 (설계 D1 단기안).

스키마·의미 검사 규칙을 extraction에 복사하지 않기 위해 contracts/tools/validate_contracts.py를 모듈로 불러옵니다.
폴더는 CONTRACTS_DIR 환경 변수로 바꿀 수 있고, 없으면 이 파일 위쪽 폴더에서 contracts/를 찾습니다(공통 라이브러리와 같은 방식).
"""

from __future__ import annotations

import importlib.util
import os
from functools import cache
from pathlib import Path
from types import ModuleType


def contracts_dir() -> Path:
    if os.getenv("CONTRACTS_DIR"):
        return Path(os.environ["CONTRACTS_DIR"])
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts"
        if (candidate / "tools" / "validate_contracts.py").is_file():
            return candidate
    raise FileNotFoundError("contracts/ 폴더를 찾지 못했어요 (CONTRACTS_DIR로 지정할 수 있어요)")


@cache
def tools() -> ModuleType:
    path = contracts_dir() / "tools" / "validate_contracts.py"
    spec = importlib.util.spec_from_file_location("mujuthaek_contract_tools", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
