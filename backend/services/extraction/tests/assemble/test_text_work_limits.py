"""금액 칸·이름·인용 분리의 입력 작업량을 작은 합성 문자열로 확인합니다."""

from mujuthaek_extraction.assemble import details, quotes, values


def test_amount_input_limits_are_applied_before_matching():
    amount = "1" * (values.MAX_AMOUNT_CHARS + 1)
    assert values.to_krw(amount, "원").amount_krw is None
    assert values.range_krw(amount, "원") is None
    assert values.point_readings(amount, "원") == ()


def test_name_asides_preserve_unclosed_and_original_nested_behavior():
    assert details._without_name_asides("‘이름’ (설명) 양식") == "이름  양식"
    assert details._without_name_asides("이름 (설명(추가)) 양식") == "이름 ) 양식"
    assert details._without_name_asides("(" * 32) == "(" * 32


def test_quote_boundaries_do_not_search_from_every_whitespace():
    text = "첫 문장입니다  /  두 문장입니다 \n 셋 문장입니다 … 마지막 문장입니다"
    assert [part.strip() for part in quotes.SPLIT_JOINED.split(text) if part.strip()] == [
        "첫 문장입니다",
        "두 문장입니다",
        "셋 문장입니다",
        "마지막 문장입니다",
    ]
