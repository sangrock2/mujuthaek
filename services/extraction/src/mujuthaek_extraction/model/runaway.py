"""응답 글의 반복 폭주 판단 (2026-10-24 세 번째 채점). 실행기(extract)는 받은 응답을, 스트리밍 호출(openai_responses)은 받는 도중의 글을 봅니다.

문자열 값 안에서만 봅니다. JSON 틀 「"scope":{"level":…}」은 항목마다 같은 글이 되풀이되는 것이 정상입니다.
"""

from __future__ import annotations

import re

RUNAWAY_CHUNK = 200  # 이 길이의 같은 조각이
RUNAWAY_REPEATS = 3  # 한 문자열 값 안에서 이만큼 나오면 폭주
RUNAWAY_STEP = 100  # 조각을 뽑는 간격
MAX_STRING_CHARS = 2_000  # 인용·설명 글 하나가 이보다 길면 폭주(인용은 원문 한 줄 안이고 지시는 300자 이내)
# 그림 판독은 그림 한 장의 글자를 문자열 하나에 옮겨 적어 2,000자를 넘는 것이 정상입니다(2026-11-05 sh-311087 가격표 그림 판독이
# 길이 규칙에 걸려 통째로 버려짐). 이런 호출에는 길이 규칙을 빼고 반복 규칙만 씁니다
LONG_TEXT_CALLS = frozenset({"image_text"})
JSON_STRING = re.compile(r'"((?:[^"\\]|\\.)*)(?:"|$)', re.S)


def runaway(raw: str, call_name: str | None = None) -> str | None:
    """응답 글의 반복 폭주 이유(없으면 None). 잘린 응답의 마지막(닫히지 않은) 문자열 값도 봅니다."""
    long_text = call_name in LONG_TEXT_CALLS
    for match in JSON_STRING.finditer(raw):
        value = match[1]
        if not long_text and len(value) > MAX_STRING_CHARS:
            return f"글 하나가 {len(value):,}자입니다(한도 {MAX_STRING_CHARS:,}자)"
        if len(value) < RUNAWAY_CHUNK * RUNAWAY_REPEATS:
            continue
        for start in range(0, len(value) - RUNAWAY_CHUNK + 1, RUNAWAY_STEP):
            chunk = value[start : start + RUNAWAY_CHUNK]
            if value.count(chunk) >= RUNAWAY_REPEATS:
                return f"같은 {RUNAWAY_CHUNK}자 글이 {value.count(chunk)}번 되풀이됩니다"
    return None
