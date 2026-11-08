"""결합 기반 계산: 인용문 위치, 금액 환산, 지역 코드. 네트워크·AI 호출 없음."""

import unicodedata
from pathlib import Path

import pytest

from mujuthaek_extraction.assemble.quotes import QuoteStatus, choose_near, quote_in_unit_row, resolve_item_quotes
from mujuthaek_extraction.assemble.regions import SOURCE_SIDO, RegionCodeTable, from_collector_code
from mujuthaek_extraction.assemble.values import to_krw

NOTICE = (
    "1. 신청자격 — 청년\n"
    "무주택세대구성원으로서 소득 70% 이하인 분\n"
    "2. 신청자격 — 신혼부부\n"
    "무주택세대구성원으로서 소득 100% 이하인 분\n"
    "전용면적 26.37㎡, 임대보증금 1,200만원"
)


def one(text, quote):
    return resolve_item_quotes(text, [quote])[0]


# ---------- 인용문 위치 ----------


def test_unique_exact_quote_gets_code_point_span():
    result = one(NOTICE, "소득 100% 이하")
    assert result.status is QuoteStatus.FOUND and result.exact
    start, end = result.span
    assert NOTICE[start:end] == "소득 100% 이하"


def test_whitespace_and_width_differences_are_mapped_back_to_original():
    result = one(NOTICE, "임대보증금  １,２００만원")  # 공백 두 칸, 전각 숫자
    assert result.status is QuoteStatus.FOUND and not result.exact
    start, end = result.span
    assert NOTICE[start:end] == "임대보증금 1,200만원"


def test_compatibility_characters_are_normalized():
    result = one(NOTICE, "26.37m2")  # 원문은 ㎡
    start, end = result.span
    assert NOTICE[start:end] == "26.37㎡"


def test_decomposed_hangul_in_source_is_matched_and_span_covers_original_jamo():
    source = unicodedata.normalize("NFD", "청년 매입임대 입주자 모집")  # PDF 텍스트에서 자모가 분해된 경우
    result = one(source, "매입임대 입주자")
    assert result.status is QuoteStatus.FOUND
    start, end = result.span
    assert unicodedata.normalize("NFC", source[start:end]) == "매입임대 입주자"


def test_repeated_quote_uses_nearest_quote_of_same_item():
    results = resolve_item_quotes(NOTICE, ["무주택세대구성원으로서", "소득 100% 이하"])
    repeated, anchor = results
    assert anchor.status is QuoteStatus.FOUND
    assert repeated.status is QuoteStatus.CHOSEN_NEAREST and len(repeated.candidates) == 2
    assert repeated.span == repeated.candidates[1]  # 신혼부부 쪽(뒤쪽)을 고름


def test_repeated_quote_without_anchor_is_ambiguous():
    result = one(NOTICE, "무주택세대구성원으로서")
    assert result.status is QuoteStatus.AMBIGUOUS and result.span is None and len(result.candidates) == 2


def test_equal_distance_is_ambiguous():
    text = "가나다라 기준문장 가나다라"
    results = resolve_item_quotes(text, ["가나다라", "기준문장"])
    assert results[0].status is QuoteStatus.AMBIGUOUS


def test_long_repeated_quote_without_anchor_uses_first_place():
    text = "요약: 2026.07.23.(목) 오전 10시부터 현장 접수합니다.\n본문: 2026.07.23.(목) 오전 10시부터 현장 접수합니다."
    result = one(text, "2026.07.23.(목) 오전 10시부터 현장 접수합니다.")
    assert result.status is QuoteStatus.CHOSEN_FIRST and result.span == result.candidates[0] and len(result.candidates) == 2


def test_missing_and_short_quotes_are_flagged():
    missing = one(NOTICE, "소득 50% 이하")
    assert missing.status is QuoteStatus.NOT_FOUND and missing.span is None
    short = one(NOTICE, "청년")
    assert short.too_short


def test_unit_row_quote():
    row = {"houseType": "26A", "areaM2": 26.37, "checks": ["deposit_won=100"]}
    assert quote_in_unit_row(row, "26 A")
    assert not quote_in_unit_row(row, "deposit_won")  # collector 메모는 원문이 아님


# ---------- 금액 ----------


@pytest.mark.parametrize(
    ("amount", "unit", "expected"),
    [
        ("1,000", "만원", 10_000_000),
        ("100000", "원", 100_000),
        ("1.5", "억원", 150_000_000),
        ("12,000", "천원", 12_000_000),
        ("1,200만원", None, 12_000_000),
        ("1억 2,000만", "원", 120_000_000),
        ("3억5천만원", None, 350_000_000),
        ("5천만", "원", 50_000_000),
        ("1천2백만원", None, 12_000_000),
        ("2억 3,500", "원", 200_003_500),
        ("0", "원", 0),
    ],
)
def test_amount_conversion(amount, unit, expected):
    result = to_krw(amount, unit)
    assert result.amount_krw == expected and result.reason is None


@pytest.mark.parametrize(
    ("amount", "unit"),
    [("공고문 참조", None), ("1,000", "달러"), ("12.345", "원"), (None, "원"), ("", "원"), ("-100", "원"), ("1,000만", "만원")],
)
def test_unconvertible_amount_is_none_with_reason(amount, unit):
    result = to_krw(amount, unit)
    assert result.amount_krw is None and result.reason


# ---------- 지역 코드 ----------

# 테스트 전용 일부 표 (형식만 법정동코드 전체 자료와 같음. 운영 코드표가 아님)
ROWS = [
    ("1100000000", "서울특별시", True),
    ("1111000000", "서울특별시 종로구", True),
    ("1111010100", "서울특별시 종로구 청운동", True),
    ("1114000000", "서울특별시 중구", True),
    ("1168000000", "서울특별시 강남구", True),
    ("1168010100", "서울특별시 강남구 역삼동", True),
    ("2600000000", "부산광역시", True),
    ("2611000000", "부산광역시 중구", True),
    ("2900000000", "광주광역시", True),
    ("4100000000", "경기도", True),
    ("4161000000", "경기도 광주시", True),
    ("4300000000", "충청북도", True),
    ("4311000000", "충청북도 청주시", True),
    ("4311100000", "충청북도 청주시 상당구", True),
    ("4700000000", "경상북도", True),
    ("4772000000", "경상북도 군위군", False),  # 폐지된 코드는 쓰지 않음
]
TABLE = RegionCodeTable(ROWS, reference_date="2026-10-15")


@pytest.mark.parametrize(
    ("region", "code", "level"),
    [
        ("서울특별시 종로구 청운동", "1111010100", "DONG"),
        ("서울시 종로구", "1111000000", "SIGUNGU"),
        ("서울 강남구 역삼동 123-4", "1168010100", "DONG"),
        ("충청북도 청주시 상당구", "4311100000", "SIGUNGU"),
        ("충북 청주시", "4311000000", "SIGUNGU"),
        ("경기도 광주시", "4161000000", "SIGUNGU"),
        ("서울특별시", "1100000000", "SIDO"),
        ("서울특별시 종로구 가상로 1", "1111000000", "SIGUNGU"),
    ],
)
def test_region_lookup(region, code, level):
    match = TABLE.lookup(region)
    assert (match.code, match.level) == (code, level)


def test_administrative_dong_falls_back_to_sigungu_with_note():
    match = TABLE.lookup("서울특별시 강남구 역삼1동")
    assert match.code == "1168000000" and match.level == "SIGUNGU" and "행정동" in match.note


def test_same_name_sigungu_needs_sido():
    assert TABLE.lookup("중구").code is None
    assert TABLE.lookup("부산광역시 중구").code == "2611000000"
    assert TABLE.lookup("중구", default_sido="서울특별시").code == "1114000000"


def test_unknown_or_retired_region_is_not_guessed():
    assert TABLE.lookup("경상북도 군위군").code == "4700000000"  # 폐지 코드 대신 시도 단위 + 메모
    assert TABLE.lookup("경상북도 군위군").note
    assert TABLE.lookup("광주 북구").code is None  # '광주'만으로는 광주광역시·경기 광주시 구별 불가
    assert TABLE.lookup(None).code is None


def test_collector_five_digit_code_is_zero_filled():
    assert from_collector_code("11110") == "1111000000"
    assert from_collector_code(None) is None
    assert from_collector_code("123") is None


OFFICIAL = Path(__file__).resolve().parents[1] / "data" / "legal-dong-codes" / "legal_dong_20260929.csv"


@pytest.mark.parametrize(
    ("region", "code"),
    [
        ("충청북도 청주시 상당구 지북동", "4311112800"),  # LH 청주지북 (마이홈 pnu 앞 10자리와 같음)
        ("전북 군산시", "5213000000"),
        ("강원도 태백시", "5119000000"),  # 강원특별자치도 개편 후 코드
        ("서울특별시 종로구 청운동", "1111010100"),
        ("광주광역시 광산구", "1233000000"),  # 전남광주통합특별시 통합 후 코드 (공고문은 옛 이름 사용)
        ("전라남도 목포시", "1211000000"),
        ("전남 목포시", "1211000000"),
    ],
)
def test_official_legal_dong_table(region, code):
    table = RegionCodeTable.from_csv(OFFICIAL, reference_date="2026-09-29")
    assert table.lookup(region).code == code


@pytest.mark.parametrize(
    ("region", "address", "code"),
    [
        # 실측 녹화 165건(2026-10-20)에서 시도까지만 남던 위치들: 서비스는 시군구(앞 5자리)를 쓰므로 주소로 다시 찾습니다
        ("대전광역시", "대전광역시 동구 옥천로 152-9", "3011000000"),  # 지역 칸은 시도뿐, 주소에 구
        ("울산광역시", "달동 1279-1", "3114010500"),  # 주소에 동만: 울산에서 달동은 남구 하나뿐
        ("울산광역시", "방어동 481-97", "3117010100"),
        ("대구", "대구북구노원로10길40", "2723000000"),  # 띄어쓰기 없는 주소
        ("충남 당진 송산면", "충남 당진 송산면", "4427039000"),  # 「시」를 뺀 지명
        ("전주", "전주시 덕진구 인교5길 17", "5211300000"),  # 일반구까지(서비스 5자리: 전주시 52110과 덕진구 52113은 다른 지역)
        ("전북 전주시", "전주시 완산구 강당2길 35-61", "5211100000"),
        ("충청북도 청주시", None, "4311000000"),  # 주소가 없으면 시까지
        ("서울특별시", "중구 세종대로 110", "1114000000"),
    ],
)
def test_region_resolved_down_to_sigungu_from_address(region, address, code):
    table = RegionCodeTable.from_csv(OFFICIAL, reference_date="2026-09-29")
    match = table.lookup(region, address=address)
    assert match.code == code, (match.code, match.note)


def test_region_from_address_is_not_guessed():
    table = RegionCodeTable.from_csv(OFFICIAL, reference_date="2026-09-29")
    assert table.lookup("경기도", address="신장동").code == "4100000000"  # 신장동은 하남시·오산시 둘 → 시도까지만
    assert table.lookup("광주").code is None  # 광주광역시·경기 광주시 구별 불가
    assert table.lookup("제주시").code == "5011000000"  # 「제주」+「시」로 떼지 않음
    assert table.lookup("서울특별시", address="부산광역시 중구 중앙대로 1").code == "1100000000"  # 주소가 다른 시도면 쓰지 않음
    assert table.lookup("전국").code is None and table.lookup("고양시, 김포시").code is None
    assert table.lookup("서울특별시 종로구", address="서울특별시 중구 세종대로 110").code == "1111000000"  # 다른 구 주소로 바꾸지 않음


def test_quote_joining_table_cells_without_separator_is_found():
    # PDF 표 행 "| 이름 | 비고 |"를 AI가 칸 구분자 없이 이어 인용한 경우 (군산 공고 실측)
    from mujuthaek_extraction.assemble.quotes import NormalizedText, normalize

    text = "[표 10-1]\n| 공 통 | 가족관계증명서 (상세) | • (제출대상) 배우자가 확인되지 않는 경우 |"
    found = NormalizedText(text).find_all(normalize("가족관계증명서 (상세) • (제출대상) 배우자가"))
    assert len(found) == 1 and text[found[0][0] : found[0][1]].startswith("가족관계증명서")


def test_quote_with_layout_marker_is_found():
    # AI가 프로그램이 붙인 표 표시까지 인용한 경우 (익산인화 행복주택 실측)
    from mujuthaek_extraction.assemble.quotes import candidates

    text = "[표 6-3]\n| 제출서류 | 비 고 |\n| 입주자격완화 확약서 | • (필수제출) 내용 확인 후 서명 |"
    spans, _ = candidates(text, "[표 6-3] | 입주자격완화 확약서 | • (필수제출) 내용 확인 후 서명 |")
    assert len(spans) == 1 and "입주자격완화 확약서" in text[spans[0][0] : spans[0][1]]


def test_repeated_sentence_is_placed_by_target_group():
    # 행복주택: 같은 문장이 계층마다 반복될 때 항목의 대상 계층으로 위치를 고릅니다
    from mujuthaek_extraction.assemble.quotes import QuoteStatus, choose_by_target_groups, resolve_item_quotes

    text = "3-1. 대학생 계층\n① 재학 중\n② 혼인 중이 아닐 것\n" + "※ 안내 문장입니다.\n" * 10 + "3-2. 청년 계층\n① 19세 이상\n② 혼인 중이 아닐 것\n"
    [ambiguous] = resolve_item_quotes(text, ["② 혼인 중이 아닐 것"])
    assert ambiguous.status is QuoteStatus.AMBIGUOUS
    youth = choose_by_target_groups(text, ambiguous, ["청년"])
    student = choose_by_target_groups(text, ambiguous, ["대학생"])
    assert youth.status is QuoteStatus.CHOSEN_NEAREST and youth.span[0] > text.index("3-2.")
    assert student.span[0] < text.index("3-2.")
    assert choose_by_target_groups(text, ambiguous, ["고령자"]).status is QuoteStatus.AMBIGUOUS


def test_quote_with_borrowed_bullet_is_found():
    # AI가 문장 중간부터 인용하며 앞 문장의 글머리표를 붙인 경우 (익산인화 행복주택 실측)
    from mujuthaek_extraction.assemble.quotes import candidates

    text = "• 공고문은 홈페이지에서도 확인하실 수\n있으며, 금회 모집 공고는 입주자격 요건을 완화하여 모집하는 공고입니다."
    spans, _ = candidates(text, "• 금회 모집 공고는 입주자격 요건을 완화하여 모집하는 공고입니다.")
    assert len(spans) == 1 and text[spans[0][0] :].startswith("금회")
    assert candidates(text, "• 없는 문장입니다 아무데도 없는 문장")[0] == []


def test_sentence_repeated_for_each_of_items_groups_takes_first():
    # 대학생·청년에 함께 걸린 항목의 인용이 두 계층 부분에 똑같이 있으면 첫 위치를 씁니다
    from mujuthaek_extraction.assemble.quotes import QuoteStatus, choose_by_target_groups, resolve_item_quotes

    text = "3-1. 대학생 계층\n③ 소득요건 배제\n" + "※ 안내 문장입니다.\n" * 10 + "3-2. 청년 계층\n③ 소득요건 배제\n"
    [ambiguous] = resolve_item_quotes(text, ["③ 소득요건 배제"])
    both = choose_by_target_groups(text, ambiguous, ["대학생", "청년"])
    assert both.status is QuoteStatus.CHOSEN_FIRST and both.span == ambiguous.candidates[0]
    assert choose_by_target_groups(text, ambiguous, ["대학생", "고령자"]).status is QuoteStatus.CHOSEN_NEAREST


def test_quote_from_scrambled_flowchart_is_found_by_words():
    # 순서도처럼 글자가 줄 단위로 뒤섞여 읽힌 곳: 인용의 낱말이 가까이 모여 있으면 그 범위를 근거로 (남해창선 영구임대 실측)
    from mujuthaek_extraction.assemble.quotes import QuoteStatus, resolve_item_quotes

    text = (
        "안내 문장입니다.\n■ 동일순위 내 경쟁 시 선정순서\n배점 합산\n전입일자가 세대구성원 신청자\n"
        "(아래 배점기준표 추첨\n오래된 자 수가 많은 자 연령 높은 자\n참조)\n" + "다른 내용입니다.\n" * 30
    )
    quote = "동일순위 내 경쟁 시 선정순서 배점 합산 (아래 배점기준표 참조) 전입일자가 오래된 자"
    [found] = resolve_item_quotes(text, [quote])
    assert found.status is QuoteStatus.FOUND and found.scattered
    assert text[found.span[0] :].startswith("동일순위") and "참조)" in text[found.span[0] : found.span[1]]
    [missing] = resolve_item_quotes(text, ["동일순위 내 경쟁 시 선정순서 배점 합산 소득 순위가 높은 자"])
    assert missing.status is QuoteStatus.NOT_FOUND


def test_amount_with_per_unit_suffix_is_converted():
    # 청년 전세임대 지원한도액 실측: "120백만" / "원/호"
    assert to_krw("120백만", "원/호").amount_krw == 120_000_000
    assert to_krw("1,200", "만원/월").amount_krw == 12_000_000


def test_single_province_source_fills_omitted_sido():
    # SH·부산도시공사 공고는 "중구"처럼 시도를 생략하기도 합니다. 출처가 한 시도뿐인 기관이면 그 시도로 찾습니다.
    table = RegionCodeTable.from_csv(OFFICIAL, reference_date="2026-09-29")
    assert table.lookup("중구").code is None  # 같은 이름의 구가 여러 시도에 있음
    assert table.lookup("중구", SOURCE_SIDO["sh"]).code == "1114000000"
    assert table.lookup("중구", SOURCE_SIDO["bmc"]).code == "2611000000"


def test_region_outside_source_province_is_not_forced_into_it():
    # 검토 지적: SH 공고의 "하남시 감일동"이 서울 코드(1100000000)로 들어갔음 — 기본 시도는 원문에 시도가 없을 때의 짐작일 뿐
    table = RegionCodeTable.from_csv(OFFICIAL, reference_date="2026-09-29")
    assert table.lookup("하남시 감일동", SOURCE_SIDO["sh"]).code.startswith("41450")
    assert table.lookup("서울특별시 하남시", SOURCE_SIDO["sh"]).code in (None, "1100000000")  # 원문이 시도를 적었으면 그 시도 안에서만


def test_long_repeated_quote_follows_target_group_not_first_occurrence():
    # 검토 지적: 15자 이상 반복 문장은 대상 계층을 보기 전에 첫 위치로 정해져 신혼부부 조건 근거가 청년 부분을 가리켰음
    from mujuthaek_extraction.assemble.quotes import choose_by_target_groups, resolve_item_quotes

    sentence = "전년도 도시근로자 월평균소득 100% 이하인 자"
    text = f"가. 청년\n{sentence}\n나. 신혼부부\n{sentence}\n"
    (resolution,) = resolve_item_quotes(text, [sentence])
    chosen = choose_by_target_groups(text, resolution, ["신혼부부"])
    assert chosen.span[0] == text.rindex(sentence)
    assert choose_by_target_groups(text, resolution, []).span[0] == text.index(sentence)  # 계층이 없으면 첫 위치 그대로


def test_eok_followed_by_bare_cheon_is_ambiguous_not_guessed():
    # 검토 지적: 「2억5천」을 200,005,000원으로 조용히 읽었음(말로는 대개 2억 5천만)
    assert to_krw("2억5천", "원").amount_krw is None and "모호" in to_krw("2억5천", "원").reason
    assert to_krw("2억5천만", "원").amount_krw == 250_000_000
    assert to_krw("2억 5,000만원", None).amount_krw == 250_000_000
    assert to_krw("1억 2,345", "원").amount_krw == 100_002_345  # 숫자로 적힌 끝자리는 그대로


def test_amount_written_only_as_a_range_is_read_as_a_range():
    # 실측: 대전도시공사 정정공고 엑셀의 단지별 임대료가 「1,200만~1,500만」처럼 범위
    from mujuthaek_extraction.assemble.values import range_krw

    assert range_krw("1,200만~1,500만", None) == (12_000_000, 15_000_000)
    assert range_krw("12,000,000 ~ 15,000,000", "원") == (12_000_000, 15_000_000)
    assert range_krw("1,200~1,500만원", None) == (12_000_000, 15_000_000)  # 뒤쪽 단위를 앞쪽에도
    assert range_krw("1,500만~1,200만", None) is None  # 거꾸로 된 범위는 짐작하지 않음
    assert range_krw("10,000", "원") is None


def test_ambiguous_short_cell_takes_the_place_next_to_the_previous_item():
    # 실측(2026-10-18 LH 강릉 영구임대): 배점표의 「보훈대상자」가 자격 설명에도 있어 위치를 못 정하고 가점 행이 빠짐
    text = "1순위 국가유공자 보훈대상자 등 자격 설명 " + "가" * 400 + " 배점표 3 국가유공자 보훈대상자 참전유공자"
    [found] = resolve_item_quotes(text, ["보훈대상자"])
    assert found.status is QuoteStatus.AMBIGUOUS
    previous = (text.rindex("국가유공자"), text.rindex("국가유공자") + 5)  # 바로 앞 가점 행의 근거
    chosen = choose_near(found, previous)
    assert chosen.status is QuoteStatus.CHOSEN_NEAREST and chosen.span[0] == text.rindex("보훈대상자")
    assert choose_near(found, None) is found  # 앞 항목 근거가 없으면 그대로


def test_cell_with_two_amounts_is_not_read_as_one_number():
    # 실측(2026-10-18 LH 포항 행복주택): 전환 증액·감액 보증금이 한 칸 「12,614 2,614」(천원)로 읽혀 1,261억 원이 자동 게시됨
    assert to_krw("12,614 2,614", "천원").amount_krw is None
    assert to_krw("57,810 86,970", "원").amount_krw is None
    assert to_krw("12,614", "천원").amount_krw == 12_614_000
    assert to_krw("3억 5천만", "원").amount_krw == 350_000_000  # 단위 글자 사이 공백은 한 금액


def test_point_followed_by_three_digits_is_not_guessed():
    # 실측(2026-11-07 jbdc-16011): 계약금 칸 「18,400.000」(보증금 92,000,000 = 18,400,000 + 잔금 73,600,000)이 18,400원으로 자동 게시됨
    for amount, unit in (("18,400.000", "원"), ("389.000", "원"), ("12.500", "천원"), ("1.234 억원", None)):
        result = to_krw(amount, unit)
        assert result.amount_krw is None and "마침표" in result.reason
    assert to_krw("1.5", "억원").amount_krw == 150_000_000  # 소수점 한두 자리는 그대로 읽음
    assert to_krw("2.25", "만원").amount_krw == 22_500
    assert to_krw("18,400,000", "원").amount_krw == 18_400_000


def test_cell_carrying_the_same_unit_as_its_column_uses_the_unit_once():
    # 실측(2026-11-07 23건 대조 gndc): 열 단위 「만원」인 표의 칸 「100만원」·「7만원」 14개가 해석할 수 없는 표기로 남음
    assert to_krw("100만원", "만원").amount_krw == 1_000_000
    assert to_krw("7 만원", "만원").amount_krw == 70_000
    assert to_krw("1,500천원", "천원").amount_krw == 1_500_000
    assert to_krw("1,000만", "만원").amount_krw is None  # 칸의 「만」과 열 단위 「만원」이 겹친 것인지 정할 수 없음
    assert to_krw("1억 2,000만원", "만원").amount_krw is None  # 칸에 다른 단위가 섞임


def test_equally_near_candidates_stay_ambiguous():
    # 검토 지적: 앞 항목 근거가 두 후보를 모두 덮어 거리가 둘 다 0이면 「0 <= 0 * 0.5」로 첫 후보를 골랐음
    text = "가점표 보훈대상자 설명 보훈대상자 끝"
    [found] = resolve_item_quotes(text, ["보훈대상자"])
    assert found.status is QuoteStatus.AMBIGUOUS and len(found.candidates) == 2
    covering = (0, len(text))
    assert choose_near(found, covering) is found


# ---------- AI가 원문 모양을 바꿔 적은 인용(2026-10-20 LH 인천부평) ----------


def test_lines_joined_with_slash_are_found_in_the_source():
    # 원문 두 줄 「- 대학생 : …⏎- 취업준비생 : …」을 「 / 」로 이어 붙이고 둘째 줄 글머리표를 뺀 인용
    text = "① 대학생 계층\n- 대학생 : 대학에 재학 중이거나 다음 학기에 입·복학 예정인 사람\n- 취업준비생 : 대학 또는 고등학교를 졸업한 지 2년 이내인 사람\n"
    quote = "- 대학생 : 대학에 재학 중이거나 다음 학기에 입·복학 예정인 사람 / 취업준비생 : 대학 또는 고등학교를 졸업한 지 2년 이내인 사람"
    [found] = resolve_item_quotes(text, [quote])
    assert found.status is QuoteStatus.FOUND and text[found.span[0] : found.span[1]].endswith("2년 이내인 사람")
    # 사이에 다른 문장이 끼면(이어진 줄이 아님) 찾지 않습니다
    apart = text.replace("\n- 취업준비생", "\n소득이 있는 사람은 제외합니다.\n- 취업준비생")
    assert resolve_item_quotes(apart, [quote])[0].status is QuoteStatus.NOT_FOUND


def test_table_row_quote_with_merged_cell_filled_is_that_row():
    # 원문 「|  |  | 1인 | 120% |…」(2인은 위 행과 병합) → 인용 「| | 2인 | | 1인 | 120% |…」
    text = (
        "| 구분 | 가구원 수 | 자녀 수 | 적용 소득기준 | 총자산가액 |\n"
        "| 세대주인 청년 | 2인 | 0인 | 110% | 251,000,000원 |\n"
        "  ↳ 세대주인 청년 2인 0인 — 적용 소득기준 110%\n"
        "|  |  | 1인 | 120% | 276,000,000원 |\n"
    )
    [found] = resolve_item_quotes(text, ["| | 2인 | | 1인 | 120% | 276,000,000원 |"])
    assert found.status is QuoteStatus.FOUND and text[found.span[0] : found.span[1]] == "|  |  | 1인 | 120% | 276,000,000원 |"
    # 원문 행의 값(120%)을 다르게 적었거나, 병합 복원으로 설명되지 않는 값(3인)이 있으면 그 행이 아닙니다
    for wrong in ("| | 2인 | | 1인 | 110% | 276,000,000원 |", "| | 3인 | | 1인 | 120% | 276,000,000원 |"):
        assert resolve_item_quotes(text, [wrong])[0].span != found.span


def test_digit_groups_that_are_not_three_digits_are_not_guessed():
    # 2026-11-09 유료 확인 sh-310672: 청년 총자산 「2억5,4000만 원 이하」를 7.4억으로 읽은 조건이 근거 확인을 통과해 자동 게시됨
    for amount in ("2억5,4000만원", "12,30", "1,0000"):
        result = to_krw(amount, None if "원" in amount else "원")
        assert result.amount_krw is None and "자릿수 쉼표" in result.reason
    assert to_krw("2억5,400만원", None).amount_krw == 254_000_000  # 세 자리씩이면 그대로 읽음
    assert to_krw("1,234,567", "원").amount_krw == 1_234_567


def test_point_or_comma_amount_gives_both_readings_for_the_caller_to_choose():
    # 2026-11-09 jbdc-16011: 「18,400.000」은 자릿수 쉼표 오타(18,400,000)인지 소수점(18,400)인지 글자만으로는 모름 — 같은 요금안의 합으로 고름
    from mujuthaek_extraction.assemble.values import point_readings

    assert point_readings("18,400.000", "원") == (18_400_000, 18_400)
    assert point_readings("12.500", "천원") == (12_500_000, 12_500)
    assert point_readings("18,400,000", "원") == ()  # 모호하지 않은 금액
    assert point_readings("1.5", "억원") == ()
