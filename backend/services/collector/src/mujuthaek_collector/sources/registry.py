"""출처 목록. 스케줄러는 ORDER 순서대로 하나씩 수집해요 (동시에 돌리지 않음)."""

from mujuthaek_collector.sources.base import Source
from mujuthaek_collector.sources.lh.source import LhSource
from mujuthaek_collector.sources.local.apply_center import ApplyCenterSource
from mujuthaek_collector.sources.local.dcco import DccoSource
from mujuthaek_collector.sources.local.dudc import DudcSource
from mujuthaek_collector.sources.local.gbgn import GbgnSource
from mujuthaek_collector.sources.local.ih import IhSource
from mujuthaek_collector.sources.local.sh import ShSource
from mujuthaek_collector.sources.local.soco import SocoSource
from mujuthaek_collector.sources.local.umca import UmcaSource

ORDER = ["sh", "gh", "bmc", "ih", "dcco", "dudc", "umca", "gbdc", "gndc", "soco", "lh"]


def build_sources() -> dict[str, Source]:
    sources: list[Source] = [
        ShSource(),
        ApplyCenterSource("gh"),
        ApplyCenterSource("bmc"),
        IhSource(),
        DccoSource(),
        DudcSource(),
        UmcaSource(),
        GbgnSource("gbdc"),
        GbgnSource("gndc"),
        SocoSource(),
        LhSource(),
    ]
    by_code = {s.code: s for s in sources}
    assert set(by_code) == set(ORDER), "registry.ORDER와 출처 목록이 달라요"
    return by_code


SOURCES = build_sources()


def get(code: str) -> Source:
    if code not in SOURCES:
        raise SystemExit(f"모르는 출처예요: {code} (가능: {', '.join(ORDER)})")
    return SOURCES[code]
