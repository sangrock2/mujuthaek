"""collector가 S3(로컬 MinIO)에 둔 자료 읽기: 잘린 원문 전체(textKey)와 첨부 원본(s3Key).

intake.SourceReader를 따릅니다. 없는 키는 None을 돌려줘 intake가 WAITING_SOURCE로 처리합니다.
권한 없음·잘못된 인증·연결 실패 같은 설정 문제는 None으로 숨기지 않고 예외로 올려 작업을 FAILED로 남깁니다(로그에 남고 제한 재시도).
예전엔 모든 오류를 "아직 없음"으로 봐서, 운영 IAM 역할이 잘못돼도 모든 공고가 조용히 자료 대기에 머물렀습니다(검토 2026-10-16).
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)
MISSING_CODES = {"NoSuchKey", "404", "NotFound"}
MAX_OBJECT_BYTES = 100 * 1024 * 1024  # 공고 PDF·첨부는 보통 수 MB. 이보다 크면 메모리를 지키려고 읽지 않습니다(검토 2026-10-16)


class SourceTooLarge(Exception):
    """S3 자료가 너무 커서 읽지 않았습니다(작업은 FAILED로 남아 사람이 봅니다)."""


class S3SourceReader:
    """S3(로컬 MinIO 포함) 버킷에서 원문 글자와 첨부 원본을 읽는 intake.SourceReader 구현입니다."""

    def __init__(self, bucket: str, endpoint: str | None, access_key: str | None, secret_key: str | None, client=None):
        if client is None:
            import boto3

            client = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access_key, aws_secret_access_key=secret_key)
        self.bucket = bucket
        self.client = client

    def _get(self, key: str) -> bytes | None:
        """키의 내용을 바이트로 읽습니다. 없는 키면 None, 너무 크면 SourceTooLarge, 그 밖의 오류는 그대로 올립니다."""
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            length = response.get("ContentLength")
            if isinstance(length, int) and length > MAX_OBJECT_BYTES:
                raise SourceTooLarge(f"{key}: {length}바이트")
            data = response["Body"].read(MAX_OBJECT_BYTES + 1)  # 길이를 안 알려 주는 저장소도 한도까지만 읽습니다
            if len(data) > MAX_OBJECT_BYTES:
                raise SourceTooLarge(f"{key}: {MAX_OBJECT_BYTES}바이트 초과")
            return data
        except SourceTooLarge:
            log.warning("S3 자료가 너무 커서 읽지 않았습니다", extra={"key": key})
            raise
        except Exception as error:
            code = str(((getattr(error, "response", None) or {}).get("Error") or {}).get("Code") or "")
            if code in MISSING_CODES:
                log.info("S3 자료가 아직 없습니다", extra={"key": key})
                return None
            log.warning("S3 자료를 읽을 수 없습니다(설정 확인)", extra={"key": key, "error": type(error).__name__, "code": code or None})
            raise

    def read_text(self, key: str) -> str | None:
        data = self._get(key)
        return data.decode("utf-8-sig") if data is not None else None  # BOM이 붙은 글자도 같은 글자로

    def read_file(self, key: str) -> bytes | None:
        return self._get(key)
