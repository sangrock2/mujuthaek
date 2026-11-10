"""프로그램이 섹션 범위를 스스로 PARTIAL로 바꿀 때 쓰는 사유.

이 사유의 PARTIAL은 형식·근거가 맞지 않는 항목을 자동으로 뺀 결과이고, 뺀 항목은 이슈·notes에 따로 남습니다.
그 밖의 PARTIAL은 AI가 "원문에 있는데 다 옮기지 못했다"고 스스로 적은 것이라 검증기가 재확인·검수로 보냅니다
(실측: 가점표·일정을 일부만 옮기고 PARTIAL로 적은 결과가 판정 섹션이 아니라는 이유로 자동 완료되던 것, 2026-10-16).
"""

DROPPED_INVALID = "형식이 맞지 않는 항목을 뺐습니다."
DROPPED_NO_EVIDENCE = "근거를 확인하지 못한 항목을 제외했습니다."
FIXED_BY_CHECK = "검사 결과에 맞게 고쳤습니다."
DROPPED_BY_CONTRACT = "계약 검사를 통과하지 못한 항목을 뺐습니다."
SYSTEM_REASONS = frozenset({DROPPED_INVALID, DROPPED_NO_EVIDENCE, FIXED_BY_CHECK, DROPPED_BY_CONTRACT})


def self_reported_partial(entry: dict | None) -> bool:
    """AI가 스스로 적은 PARTIAL인가(프로그램이 항목을 빼서 바꾼 PARTIAL이 아닌가)."""
    return bool(entry) and entry.get("status") == "PARTIAL" and entry.get("reason") not in SYSTEM_REASONS
