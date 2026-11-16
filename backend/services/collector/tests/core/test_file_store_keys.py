"""S3 키 조각: 정리한 결과가 같아도 서로 다른 글·첨부는 다른 키를 써요 (2026-11-16 보안 감사 4장)."""

import re

import pytest

from mujuthaek_collector.core.file_store import object_key, safe_part, text_key

KEY_SEGMENT = re.compile(r"[0-9A-Za-z가-힣._\-~]+")


@pytest.mark.parametrize("value", ["12345", "43-1", "모집공고문.pdf", "a.b", "공고_v2.hwp"])
def test_clean_values_keep_the_same_key_as_before(value):
    assert safe_part(value, 120) == value


@pytest.mark.parametrize(
    ("first", "second"),
    [("a/b", "a_b"), ("a/b", "a:b"), ("x" * 81, "x" * 82), ("rent:1:2", "rent_1_2"), ("모집 공고문.pdf", "모집_공고문.pdf"), ("", "file")],
)
def test_values_that_clean_to_the_same_text_get_different_keys(first, second):
    assert safe_part(first) != safe_part(second)
    assert object_key("lh", first, 1, 0, "a.pdf") != object_key("lh", second, 1, 0, "a.pdf")
    assert text_key("lh", first, 1) != text_key("lh", second, 1)


@pytest.mark.parametrize("value", ["..", ".", "...", "a..b.pdf", "../../etc", "a\\b", "x\ny", "가" * 200, "<script>"])
def test_parts_are_single_safe_segments_within_limit(value):
    part = safe_part(value, 80)
    assert KEY_SEGMENT.fullmatch(part) and len(part) <= 80
    assert ".." not in part and part not in {".", ""}


def test_extension_stays_at_the_end_when_hashed():
    part = safe_part("모집 공고문(최종).hwp", 120)
    assert part.endswith(".hwp") and "~" in part
    assert object_key("dcco", "1", 1, 0, "모집 공고문(최종).hwp").startswith("raw/dcco/1/v1/00-모집_공고문_최종")
