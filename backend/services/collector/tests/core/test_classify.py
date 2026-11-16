import re
import time
from datetime import date

import pytest

import mujuthaek_collector.core.classify as titles
from mujuthaek_collector.core.classify import (
    CORRECTION,
    CORRECTION_MARK,
    EXCLUDED,
    FOLLOW_UP,
    NOT_IDENTITY,
    NOTICE,
    QUALIFIER,
    classify,
    correction_base,
    find_ref,
    norm_name,
    qualifiers,
    ref_qualifiers,
    same_notice,
    same_qualifiers,
    title_ref,
)


@pytest.mark.parametrize(
    ("title", "kind"),
    [
        ("2026년 하반기 신혼·신생아 매입임대주택Ⅱ 입주자 모집공고", NOTICE),
        ("2026년 행복주택 입주자 모집공고 [정정공고]", CORRECTION),
        ("성북구 연극인주택 잔여세대 입주자 모집공고(26. 7. 8.) 당첨자발표 및 계약안내", FOLLOW_UP),
        ("2026년 기존주택 매입 공고", EXCLUDED),
        ("○○지구 공동주택용지 공급 공고", EXCLUDED),
        ("임대아파트 단지 내 상가 입점자 모집 공고", EXCLUDED),
        ("임대주택 재계약 안내", EXCLUDED),
        ("2026년 국민임대 예비입주자 모집공고", NOTICE),
        # 대전 실제 제목 (2026-10-15)
        ("2026년 2차 영구임대아파트 예비입주자 모집공고", NOTICE),
        ("낭월 다가온 청년주택 추가모집 공고", NOTICE),
        ("2026년 기존주택(청년임대) 3차 매입공고", EXCLUDED),
        ("2026년 기존주택(청년) 추가 매입 공고", EXCLUDED),
        ("갑천2 트리풀시티 엘리프 단지 내 상가 수의계약 공고", EXCLUDED),
        ("대전평촌일반산업단지 산업ㆍ복합시설용지 일반공급 3차 공고", EXCLUDED),
        # 인천·서울 실제 제목 (2026-10-19): 특화시설 운영자 모집은 제외, '(운영기관 : ○○)'은 입주자 모집
        ("2026년 우리집 특화시설 운영자 모집공고(수시)", EXCLUDED),
        ("2026년 공모형 매입임대주택 특화시설 운영자 모집공고(정기)", EXCLUDED),
        ("[청년형] 특화형 매입임대주택(금천구) 입주자 모집 공고(운영기관 : 한지붕협동조합)", NOTICE),
        # 인천·울산 실제 제목 (2026-10-20): 첨부 없는 안내·알림은 후속 안내, 심사·동호배정 결과는 그대로 제외
        ("2026년 기존주택 매입임대(청년형) 예비입주자 선정 안내", FOLLOW_UP),
        ("2026년 매입임대주택(청년형) 예비입주자 선정 발표 지연 안내", FOLLOW_UP),
        ("2026년 매입임대주택(일반형) 2차 예비입주자 입주안내", FOLLOW_UP),
        ("2026년 매입임대주택(청년형) 예비입주자 일정 안내", FOLLOW_UP),
        ("유홈(U home) 신정 청년주택 자격완화 예비입주자 모집 종료 알림", FOLLOW_UP),
        ("문수데시앙3단지 국민임대주택(46㎡) 예비입주자 2차 모집 중단 안내", FOLLOW_UP),
        ("성안동 청년희망주택 예비입주자 확정 공고", FOLLOW_UP),
        ("율동위드유아파트 주거약자용 예비입주자 순번 결과 공고", FOLLOW_UP),
        ("대전평촌일반산업단지 입주협약기업 입주계약심사결과 공고", EXCLUDED),
        ("동인천역 파크푸르지오 영구임대주택 예비자 동호배정 결과 공고(26.1.30.)", EXCLUDED),
        # 2026-11-10 코드 검토: 후속 안내 단어가 무엇을 정정했는지 말할 뿐이면 정정공고 (예전엔 후속 안내로 분류)
        ("[정정공고] 2026년 행복주택 입주자 모집공고(당첨자 발표일 변경)", CORRECTION),
        ("2026년 국민임대 예비입주자 모집공고 [정정] 서류제출 대상자 발표 일정 연기", CORRECTION),
        ("[정정] 2026년 매입임대주택(청년형) 예비입주자 선정 안내", FOLLOW_UP),  # 정정한 후속 안내
        ("[정정] 행복주택 입주자 모집공고 당첨자 발표", FOLLOW_UP),
        ("2026년 행복주택 입주자 모집공고(2026.10.01) 정정공고", CORRECTION),  # 공고일 뒤 정정 표시는 후속 안내 글이 아님
        ("[정정] 행복주택 입주자 모집공고(2026.10.01) 당첨자 발표", FOLLOW_UP),
        # 2026-11-10 재검토: 공고일 뒤에 바뀐 내용을 적은 정정 제목도 정정공고 (공고일 검사가 먼저라 후속 안내로 남았음)
        ("[정정공고] 2026년 행복주택 입주자 모집공고(2026.10.01) 당첨자 발표일 변경", CORRECTION),
        ("[정정] 2026년 국민임대 입주자 모집공고(2026.10.01) 접수기간 연장", CORRECTION),
        ("2026년 행복주택 입주자 모집공고(2026. 10. 1.) 서류심사 대상자 발표", FOLLOW_UP),
    ],
)
def test_classify(title, kind):
    assert classify(title) == kind


def test_qualifiers_tell_apart_blocks_with_the_same_name():
    a2, a3 = qualifiers("행복주택 입주자 모집공고(A-2블록) [정정공고]"), qualifiers("행복주택 입주자 모집공고(A-3블록)")
    assert a2 == frozenset({"A2블록"}) and not same_qualifiers(a2, a3)
    assert same_qualifiers(a2, qualifiers("행복주택 입주자 모집공고(A-2블록)(수요자맞춤형)"))  # 꾸밈말을 더하거나 빼도 같은 공고
    assert same_qualifiers(frozenset(), a3)


def test_dates_and_what_changed_are_not_qualifiers():
    # 2026-11-10 재검토: 공고일·바뀐 내용 괄호까지 견줘, 꾸밈말이 다른 원래 공고와 정정공고가 끊겼음
    fixed = qualifiers("[정정] 행복주택 입주자 모집공고(A-2블록)(2026.10.01 공고)(당첨자 발표일 변경)")
    assert fixed == frozenset({"A2블록"})
    assert same_qualifiers(fixed, qualifiers("행복주택 입주자 모집공고(A-2블록)(수요자맞춤형)"))
    assert qualifiers("국민임대 모집공고(재공고)") == frozenset()
    assert qualifiers("국민임대 모집공고(2026년 10월)") == frozenset({"2026년10월"})  # 회차는 공고를 가름


def test_follow_up_points_to_original_notice():
    ref = title_ref("성북구 연극인주택 잔여세대 입주자 모집공고(26. 7. 8.) 당첨자발표 및 계약안내")
    assert ref is not None and ref.posted_on == date(2026, 7, 8)
    assert same_notice(ref, "성북구 연극인주택 잔여세대 입주자 모집공고", date(2026, 7, 8))
    assert not same_notice(ref, "성북구 연극인주택 잔여세대 입주자 모집공고", date(2026, 7, 9))


def test_correction_base_matches_original_name():
    assert correction_base("2026년 행복주택 입주자 모집공고 [정정공고]") == norm_name("2026년 행복주택 입주자 모집공고")


# 2026-11-16 이전의 공고일 정규식. find_ref가 이것과 같은 결과를 내는지 견줘요 (짧은 제목이라 이 정규식도 금방 끝나요)
OLD_REF = re.compile(r"(?P<name>.+?)\s*\(\s*(?:공고일?\s*:?\s*)?[‘'’]?(?P<y>\d{2,4})\s*[._]\s*(?P<m>\d{1,2})\s*[._]\s*(?P<d>\d{1,2})\s*\.?\s*(?:공고)?\s*\)")


@pytest.mark.parametrize(
    "title",
    [
        "성북구 연극인주택 잔여세대 입주자 모집공고(26. 7. 8.) 당첨자발표 및 계약안내",
        "[정정] 행복주택 입주자 모집공고(A-2블록)(2026.10.01 공고)(당첨자 발표일 변경)",
        "행복주택 모집공고 (공고일: ‘26.08.21 공고) 서류심사 대상자 발표",
        "모집공고( 2026 . 10 . 01 . 공고 ) 결과",
        "모집공고(2026_10_01)(2026.10.02) 결과",
        "모집공고(2026.13.40) 발표",
        "모집공고(12345.1.1) 발표",
        "모집공고 (2026.10.01",
        "첫 줄\n모집공고 \t　(2026. 10. 1.) 당첨자 발표",
        "모집공고\n(2026.10.01) 줄바꿈 뒤 괄호",
        " (2026.10.01) 이름 없이 공백만",
        "\n\n(2026.10.01)\n \t(2026.10.02)",
        "(2026.10.01)",
        "",
    ],
)
def test_find_ref_gives_the_old_pattern_result(title):
    """2026-11-16 M-6: 예전 정규식은 시작 글자마다 공고명(.+?)과 공백(\\s*)을 나눠 보며 끝까지 훑어서
    공백이 긴 제목에서 세제곱으로 느려졌어요(공백 4천 자 25초)."""
    old = OLD_REF.search(title)
    assert find_ref(title) == ((old["name"], old["y"], old["m"], old["d"], old.end()) if old else None)


def test_unclosed_brackets_do_not_change_qualifiers():
    """짝 없는 여는 괄호(마지막 닫는 괄호 뒤)는 예전에도 구분 말이 되지 못했어요. 그 앞까지만 봐도 결과가 같아요."""
    title = "[정정] 행복주택 입주자 모집공고(A-2블록)(수요자맞춤형)(2026.10.01) [당첨자 (미완 ["

    def old_qualifiers(text):
        found = (re.sub(r"[^0-9A-Za-z가-힣]", "", q) for q in QUALIFIER.findall(CORRECTION_MARK.sub("", text)) if not NOT_IDENTITY.search(q))
        return frozenset(q for q in found if q)

    assert qualifiers(title) == old_qualifiers(title) == frozenset({"A2블록", "수요자맞춤형"})
    assert ref_qualifiers(title) == frozenset({"A2블록", "수요자맞춤형"})


def test_only_the_head_of_a_very_long_title_is_classified():
    """제목 판단은 앞 MAX_TITLE_CHARS자만 봐요(실제 제목은 수백 자를 넘지 않아요). 저장하는 제목은 그대로예요."""
    head = "2026년 행복주택 입주자 모집공고"
    assert classify(head + " " * 100 + "[정정공고]") == CORRECTION
    assert classify(head + " " * titles.MAX_TITLE_CHARS + "[정정공고]") == NOTICE


@pytest.mark.parametrize("limit", [titles.MAX_TITLE_CHARS, 10**9])
def test_title_checks_stay_fast_on_hostile_titles(monkeypatch, limit):
    """2026-11-16 M-6: 목록 제목마다 도는 정규식이 긴 공백·괄호·숫자에서 제곱~세제곱으로 느려졌어요(공백 4천 자 classify 25초, '(' 8천 개 1.9초).
    잘라 보는 길이를 없애도(정규식만으로도) 빨라야 해요."""
    monkeypatch.setattr(titles, "MAX_TITLE_CHARS", limit)
    hostile = [" " * 100_000, "가" * 100_000, "(" * 100_000, "[" * 100_000, "(1" * 50_000, "(정정 " * 20_000, "동" + " " * 100_000 + "x"]
    hostile.append("가" * 100_000 + "(2026.10.01) 당첨자 발표")
    started = time.perf_counter()
    for title in hostile:
        classify(title)
        title_ref(title)
        ref_qualifiers(title)
        qualifiers(title)
    assert time.perf_counter() - started < 1
    assert (title_ref(hostile[-1]) is not None) == (limit > 100_000)  # 잘라 보면 10만 자 뒤의 공고일은 안 봐요
