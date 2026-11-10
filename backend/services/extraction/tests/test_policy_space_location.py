"""사업공간 공간 위치(사업공간 2차 채점 뒤 일반 규칙): 시도 정식 이름·약칭, 확인하지 못한 공간 위치는 전국으로 내지 않음,
같은 곳의 상위 코드 빼기, 여러 공간은 이름마다 확인. 지어낸 공고 글로만 시험합니다."""

from test_policy_judgment import answer, reading, tour

from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.judgment.policy_frame import region_named
from mujuthaek_extraction.publish import narrowest, policy_completed_payload, policy_frame, policy_region_codes

SPACE_REGIONS = RegionCodeTable(
    [
        ("1100000000", "서울특별시", True),
        ("1111000000", "서울특별시 종로구", True),
        ("1144000000", "서울특별시 마포구", True),
        ("4100000000", "경기도", True),
        ("4159000000", "경기도 화성시", True),
        ("4128000000", "경기도 고양시", True),
        ("4128500000", "경기도 고양시 일산동구", True),
        ("4400000000", "충청남도", True),
        ("4413000000", "충청남도 천안시", True),
        ("4300000000", "충청북도", True),
        ("5200000000", "전북특별자치도", True),
    ],
    "2026-10-01",
)


def test_region_names_match_full_names_and_abbreviations_both_ways():
    assert region_named("충청남도 천안시", "소재지 : 충남 천안시 가상로 1")
    assert region_named("충남 천안시", "충청남도 천안시 가상로 1")
    assert region_named("전북특별자치도", "전라북도 가상군") and region_named("전라북도", "전북 가상군")
    assert region_named("강원도", "강원특별자치도 가상시") and region_named("제주특별자치도", "제주 가상읍")
    assert region_named("서울특별시 마포구", "서울시 마포구 가상로") and region_named("부산광역시", "부산 가상구")
    assert region_named("경기도 고양시", "경기 고양 가상동")
    assert not region_named("충청남도", "충북 청주시")
    assert not region_named("서울특별시 남구", "서울 북구")
    assert not region_named("광주광역시", "광주 가상동")  # 경기도 광주시와 구별할 수 없음


def space_payload(text, scope="NATIONWIDE"):
    return tour() | {"text": text, "regionScope": scope, "regionNames": [], "regionCodes": []}


def located(names, quote):
    return reading(answer([], spaceLocation={"names": names, "quote": quote}))


def test_space_location_written_with_an_abbreviation_keeps_the_sigungu():
    text = "센터 안내\n소재지 : 충남 천안시 가상로 1, 별빛센터\n"
    assert policy_region_codes(space_payload(text), SPACE_REGIONS, located(["충청남도 천안시"], "소재지 : 충남 천안시 가상로 1, 별빛센터")) == ["44130"]


def test_unverified_space_location_is_not_sent_as_nationwide():
    text = "센터 안내\n소재지 : 가상시 가상로 1, 별빛센터\n"
    claimed = located(["충청북도 청주시"], "소재지 : 가상시 가상로 1, 별빛센터")
    payload = space_payload(text)
    assert policy_region_codes(payload, SPACE_REGIONS, claimed) is None
    assert policy_completed_payload(payload, policy_frame(payload, claimed, SPACE_REGIONS), SPACE_REGIONS, claimed) is None
    # 수집기가 시도를 주면 그 값(지금까지와 같음)
    assert policy_region_codes(space_payload(text, "SIDO") | {"regionNames": ["서울"]}, SPACE_REGIONS, claimed) == ["11000"]
    # 원문에 공간 위치가 없거나 AI가 「전국」으로 읽었으면 수집기 전국 그대로
    assert policy_region_codes(payload, SPACE_REGIONS, located([], None)) == []
    assert policy_region_codes(payload, SPACE_REGIONS, located(["전국"], "소재지 : 가상시 가상로 1, 별빛센터")) == []


def test_upper_codes_of_the_same_place_are_dropped():
    assert narrowest(["41000", "41280", "41285"]) == ["41285"]
    assert narrowest(["11000", "41590"]) == ["11000", "41590"]
    assert narrowest(["41000", "41590"]) == ["41590"]
    text = "소재지\n경기도 고양시 일산동구 가상로 7, 별빛관\n"
    split = located(["경기도", "고양시", "일산동구"], "경기도 고양시 일산동구 가상로 7, 별빛관")
    assert policy_region_codes(space_payload(text), SPACE_REGIONS, split) == ["41285"]
    whole = located(["경기도", "경기도 화성시"], "경기도 화성시 가상로 3")
    assert policy_region_codes(space_payload("경기도 화성시 가상로 3\n"), SPACE_REGIONS, whole) == ["41590"]


def test_each_space_name_is_checked_on_its_own_line_and_verified_names_are_kept():
    text = "1. 센터 위치\n(서울특별시 종로구 가상로 1 2층)\n(서울특별시 마포구 가상로 2 지하 1층)\n"
    two = located(["서울특별시 종로구", "서울특별시 마포구"], "(서울특별시 종로구 가상로 1 2층)")
    assert policy_region_codes(space_payload(text), SPACE_REGIONS, two) == ["11110", "11440"]
    # 원문 어디에도 없는 이름은 빼고 확인된 이름은 남김
    stray = located(["서울특별시 종로구", "경기도 화성시"], "(서울특별시 종로구 가상로 1 2층)")
    assert policy_region_codes(space_payload(text), SPACE_REGIONS, stray) == ["11110"]
    # 근거 문장에서 멀리 떨어진 줄의 이름은 공간 위치로 보지 않음
    far = text + "\n".join(["안내"] * 5) + "\n경기도 화성시 가상로 3\n"
    assert policy_region_codes(space_payload(far), SPACE_REGIONS, stray) == ["11110"]
