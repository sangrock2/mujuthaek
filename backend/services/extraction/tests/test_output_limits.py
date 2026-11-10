"""호출별 출력 한도: 실측 최대보다 작지 않고, 폭주를 줄일 만큼 낮으며, 설정으로 바꿀 수 있는지."""

from helpers import every_call, example, source_for

from mujuthaek_extraction import supply_tables
from mujuthaek_extraction.rules.base import OUTPUT_LIMIT_ENV, output_limit
from mujuthaek_extraction.rules.housing_notice import MEASURED_MAX_OUTPUT, OUTPUT_LIMITS, RULES, RULES_V10


def all_calls():
    for rules in (RULES, RULES_V10):
        yield from every_call(rules)
        yield rules.continuation


def test_each_call_limit_is_at_least_its_measured_maximum():
    for call in all_calls():
        assert call.max_output_tokens == OUTPUT_LIMITS[call.name]
        measured = MEASURED_MAX_OUTPUT.get(call.name, MEASURED_MAX_OUTPUT["structure"])  # 이어받기는 구조와 같은 공급 묶음
        assert call.max_output_tokens >= measured * 1.25, call.name


def test_section_limits_are_below_the_old_runaway_cap():
    # 실측 0839: 선정 호출이 반복으로 48,000토큰까지 감. 나눠 부르는 섹션 호출은 그보다 낮게
    for name in ("schedules", "eligibility", "selection", "documents"):
        assert OUTPUT_LIMITS[name] < 48_000 and OUTPUT_LIMITS[name] <= round(MEASURED_MAX_OUTPUT[name] * 1.35, -3)


def test_limit_can_be_overridden_per_call(monkeypatch):
    material = source_for("housing", example("housing")).material
    selection = next(call for call in every_call(RULES) if call.name == "selection")
    assert RULES.build_request(selection, material).max_output_tokens == 28_000
    monkeypatch.setenv(OUTPUT_LIMIT_ENV, " selection = 32000 ,documents=abc,schedules=0")
    assert RULES.build_request(selection, material).max_output_tokens == 32_000
    assert output_limit("documents", 21_000) == 21_000  # 숫자가 아니면 무시
    assert output_limit("schedules", 18_000) == 18_000  # 0 이하는 무시
    assert output_limit("structure", 64_000) == 64_000
    request = RULES.build_request(RULES.calls[0], material)
    assert supply_tables.mapping_request(request, []).max_output_tokens == supply_tables.MAX_OUTPUT_TOKENS
    monkeypatch.setenv(OUTPUT_LIMIT_ENV, "supply_tables=6000")
    assert supply_tables.mapping_request(request, []).max_output_tokens == 6_000
