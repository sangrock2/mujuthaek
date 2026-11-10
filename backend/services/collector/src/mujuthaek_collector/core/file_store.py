"""원본 파일 보관 (로컬은 MinIO, AWS로 옮기면 S3). S3_ENDPOINT를 빈 값으로 주면 AWS S3를 써요.

S3 위치: raw/<출처>/<글 키>/v<버전>/<순번>-<파일명>
보관 기한: 마감일(없으면 게시일) + 6개월, 예비입주자 모집은 1년. 기한이 지나면 cleanup 명령이 파일만 지우고,
기관 다운로드 주소·해시·추출한 글자는 DB에 계속 남아요.
"""

import re
from datetime import date
from pathlib import Path
from typing import Protocol

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "hwp": "application/x-hwp",
    "hwpx": "application/hwp+zip",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "xls": "application/vnd.ms-excel",
    "txt": "text/plain; charset=utf-8",
    "csv": "text/csv",
}


class FileStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> str: ...

    def delete(self, key: str) -> None: ...

    def put_file(self, key: str, path: Path, content_type: str, metadata: dict[str, str]) -> str: ...

    def metadata(self, key: str) -> dict[str, str] | None: ...


class S3FileStore:
    def __init__(self, bucket: str, endpoint: str | None = None, access_key: str | None = None, secret_key: str | None = None):
        import boto3

        self._bucket = bucket
        self._s3 = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access_key, aws_secret_access_key=secret_key)

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    def put_file(self, key: str, path: Path, content_type: str, metadata: dict[str, str]) -> str:
        """큰 파일(상가 시도 파일 수십 MB)을 메모리에 올리지 않고 올려요. 일정 크기를 넘으면 여러 조각(multipart)으로 나눠 보내요.
        메타데이터 값은 ASCII만 돼요 (S3 규칙)."""
        with path.open("rb") as f:
            self._s3.upload_fileobj(f, self._bucket, key, ExtraArgs={"ContentType": content_type, "Metadata": metadata})
        return key

    def metadata(self, key: str) -> dict[str, str] | None:
        """객체 메타데이터 (키는 소문자). 객체가 없으면 None."""
        from botocore.exceptions import ClientError

        try:
            return self._s3.head_object(Bucket=self._bucket, Key=key)["Metadata"]
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise


def safe_part(text: str, limit: int = 80) -> str:
    """S3 키에 쓸 수 있게: 슬래시·공백·특수문자는 _로. 한글은 그대로 둬요."""
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._\-]+", "_", text).strip("_")
    return cleaned[:limit] or "file"


def object_key(source_code: str, post_key: str, version: int, idx: int, name: str) -> str:
    return f"raw/{source_code}/{safe_part(post_key)}/v{version}/{idx:02d}-{safe_part(name, 120)}"


def text_key(source_code: str, post_key: str, version: int) -> str:
    """AI에 넘길 전체 글자가 너무 길 때 따로 두는 위치."""
    return f"text/{source_code}/{safe_part(post_key)}/v{version}.txt"


def content_type(ext: str) -> str:
    return CONTENT_TYPES.get(ext, "application/octet-stream")


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    last_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(day.day, last_day))


def stored_until(title: str, deadline_on: date | None, posted_on: date | None, today: date) -> date:
    """파일 보관 기한: 마감일(없으면 게시일, 둘 다 없으면 오늘) + 6개월. 예비입주자 모집은 1년."""
    base = deadline_on or posted_on or today
    return add_months(base, 12 if re.search(r"예비\s*입주자", title) else 6)
