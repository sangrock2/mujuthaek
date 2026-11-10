"""LH API 응답 읽기. 응답 자체는 바꾸지 않고, 필요한 값만 꺼내요.

LH API 응답은 [{묶음: [...]}, {묶음: [...]}, ...] 형태예요 (예: dsSch=요청 값, dsList=목록, dsAhflInfo=첨부).
오류 응답(예: 등록되지 않은 인증키)은 배열이 아니라 객체로 와요.
"""

from __future__ import annotations

from typing import Any


class LhApiError(Exception):
    """LH API가 오류 응답을 줌."""


def merge_blocks(body: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(body, list):
        raise LhApiError(f"LH API 오류 응답: {str(body)[:300]}")
    merged: dict[str, list[dict[str, Any]]] = {}
    for block in body:
        if isinstance(block, dict):
            merged.update(block)
    return merged


def list_rows(body: Any) -> list[dict[str, str]]:
    """목록 응답의 공고 줄 (dsList)."""
    return merge_blocks(body).get("dsList", [])


def attachments(detail_body: Any) -> list[dict[str, str]]:
    """상세정보 응답의 공고 첨부파일 목록 (dsAhflInfo: 종류·파일명·AHFL_URL)."""
    return merge_blocks(detail_body).get("dsAhflInfo", [])
