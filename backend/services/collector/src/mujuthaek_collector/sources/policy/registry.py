"""정책 출처 목록. 스케줄러는 매일 POLICY_ORDER 순서대로 하나씩 수집해요."""

from mujuthaek_collector.sources.policy.base import PolicySource
from mujuthaek_collector.sources.policy.bizinfo import BizinfoSource
from mujuthaek_collector.sources.policy.bokjiro import BokjiroCentralSource, BokjiroLocalSource
from mujuthaek_collector.sources.policy.config import PolicySettings
from mujuthaek_collector.sources.policy.gov24 import Gov24Source
from mujuthaek_collector.sources.policy.kstartup import KStartupSource
from mujuthaek_collector.sources.policy.youth import YouthSource

POLICY_ORDER = ["gov24", "bokjiro_central", "bokjiro_local", "youth", "kstartup", "bizinfo"]


def build_policy_sources(settings: PolicySettings) -> dict[str, PolicySource]:
    sources: list[PolicySource] = [
        Gov24Source(settings.data_go_kr_key),
        BokjiroCentralSource(settings.data_go_kr_key),
        BokjiroLocalSource(settings.data_go_kr_key),
        YouthSource(settings.youth_key, settings.youth_categories),
        KStartupSource(settings.data_go_kr_key),
        BizinfoSource(settings.bizinfo_key),
    ]
    by_code = {s.code: s for s in sources}
    assert list(by_code) == POLICY_ORDER, "POLICY_ORDER와 정책 출처 목록이 달라요"
    return by_code


def get_policy(code: str, settings: PolicySettings) -> PolicySource:
    sources = build_policy_sources(settings)
    if code not in sources:
        raise SystemExit(f"모르는 정책 출처예요: {code} (가능: {', '.join(POLICY_ORDER)})")
    return sources[code]
