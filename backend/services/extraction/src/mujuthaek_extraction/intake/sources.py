"""collector가 보관한 자료를 읽는 인터페이스.

운영 구현은 S3(로컬 MinIO 포함)에서 읽는 s3_reader.S3SourceReader이고, 시험에서는 메모리·로컬 폴더 구현을 씁니다.
기관 다운로드 주소(downloadUrl)로는 요청하지 않습니다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from mujuthaek_extraction.intake.model import ApiReference, RawNoticeCollected


class SourceReader(Protocol):
    def read_text(self, key: str) -> str | None:
        """잘린 원문 전체 텍스트(textKey)를 읽습니다. 없으면 None입니다."""
        ...

    def read_file(self, key: str) -> bytes | None:
        """첨부 원본(s3Key)을 읽습니다. 없으면 None입니다."""
        ...


class InMemorySourceReader:
    """테스트·오프라인 실행용 리더입니다."""

    def __init__(self, texts: Mapping[str, str] | None = None, files: Mapping[str, bytes] | None = None):
        self._texts = dict(texts or {})
        self._files = dict(files or {})

    def read_text(self, key: str) -> str | None:
        return self._texts.get(key)

    def read_file(self, key: str) -> bytes | None:
        return self._files.get(key)


class LocalDirSourceReader:
    """S3 대신 로컬 폴더에서 읽습니다 (S3 키가 정해지기 전 시험용 PDF). 키는 폴더 아래 상대 경로이며 폴더 밖은 읽지 않습니다."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path | None:
        path = (self.root / key).resolve()
        return path if path.is_relative_to(self.root) and path.is_file() else None

    def read_text(self, key: str) -> str | None:
        path = self._path(key)
        return path.read_text(encoding="utf-8") if path else None

    def read_file(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path else None


class ApiReferenceProvider(Protocol):
    def find(self, raw: RawNoticeCollected) -> ApiReference | None:
        """같은 공고·같은 버전의 API 응답 원본을 찾습니다. 없으면 None입니다."""
        ...


class NoApiReference:
    """API 원본이 없는 출처(현재 지방공사 크롤링 9곳)에 사용합니다."""

    def find(self, raw: RawNoticeCollected) -> ApiReference | None:
        return None
