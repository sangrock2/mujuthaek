"""수집기가 만드는 이벤트가 contracts/events/raw.notice.collected.v1.json과 맞는지."""

from datetime import date
from uuid import UUID

import pytest
from jsonschema import ValidationError

from mujuthaek_collector.core.publisher import MAX_TEXT_CHARS, build_collected_event
from mujuthaek_platform.contracts import validate_event


def make(**overrides):
    values = dict(
        raw_post_id=UUID("01929a3e-0000-7000-8000-000000000001"),
        version=1,
        source_code="dcco",
        provider="DCCO",
        kind="NOTICE",
        title="2026년 국민임대 입주자 모집공고",
        posted_on=date(2026, 10, 1),
        detail_url="https://www.dcco.kr/web/board/view.do?mId=43&brdIdx=1",
        parent_post_id=None,
        full_text="제목: …",
        text_key=None,
        files=[
            {
                "name": "모집공고문.pdf",
                "file_type": "pdf",
                "role": "NOTICE_DOC",
                "s3_key": "raw/dcco/43-1/v1/00-모집공고문.pdf",
                "download_url": "https://www.dcco.kr/web/board/download.do?fidx=1",
                "file_hash": "ab" * 32,
            }
        ],
    )
    values.update(overrides)
    return build_collected_event(**values)


def test_event_matches_contract():
    event = make()
    validate_event(event)
    assert event["payload"]["units"] == []  # 호별 임대조건은 extraction이 원본에서 읽어요


def test_follow_up_with_parent_and_long_text():
    event = make(
        kind="FOLLOW_UP", parent_post_id=UUID("01929a3e-0000-7000-8000-000000000002"), full_text="가" * (MAX_TEXT_CHARS + 10), text_key="text/dcco/1/v1.txt"
    )
    validate_event(event)
    assert len(event["payload"]["text"]) == MAX_TEXT_CHARS and event["payload"]["textKey"] == "text/dcco/1/v1.txt"


def test_files_carry_s3_location_role_and_type():
    file = make()["payload"]["files"][0]
    assert file == {
        "name": "모집공고문.pdf",
        "fileType": "pdf",
        "role": "NOTICE_DOC",
        "s3Key": "raw/dcco/43-1/v1/00-모집공고문.pdf",
        "downloadUrl": "https://www.dcco.kr/web/board/download.do?fidx=1",
        "sha256": "ab" * 32,
    }


def test_s3_key_may_be_null_after_retention():
    """보관 기한이 지나 파일을 지운 뒤 재처리하면 s3Key 없이 보내요."""
    event = make()
    event["payload"]["files"][0]["s3Key"] = None
    validate_event(event)


@pytest.mark.parametrize("field,value", [("role", "APPLICATION_FORM"), ("fileType", "zip"), ("s3Key", "https://bucket.s3/raw/x.pdf")])
def test_wrong_file_fields_fail_contract(field, value):
    event = make()
    event["payload"]["files"][0][field] = value
    with pytest.raises(ValidationError):
        validate_event(event)


@pytest.mark.parametrize("field", ["fileType", "role", "s3Key"])
def test_file_fields_are_required(field):
    event = make()
    del event["payload"]["files"][0][field]
    with pytest.raises(ValidationError):
        validate_event(event)
