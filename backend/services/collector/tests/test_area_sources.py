from datetime import date

import pytest

from mujuthaek_collector.area import sources


def test_facility_keys():
    assert sources.s3_key("BUS_STOP", date(2025, 10, 31)) == "area/BUS_STOP/2025-10-31/bus_stop.csv"
    assert sources.s3_key("SUBWAY_STATION", date(2026, 6, 18), "ALL") == "area/SUBWAY_STATION/2026-06-18/subway_station.csv"


def test_store_keys_use_english_sido_names():
    assert sources.s3_key("STORES", date(2026, 6, 30), "강원") == "area/STORES/2026-06-30/stores_gangwon.csv"
    assert sources.s3_key("STORES", date(2026, 6, 30), "전남광주") == "area/STORES/2026-06-30/stores_jeonnam_gwangju.csv"
    assert len(sources.STORES_SCOPES) == 16


def test_address_entrance_keys_use_the_file_sido_code():
    assert sources.s3_key("ADDRESS_ENTRANCE", date(2026, 9, 30), "36") == "area/ADDRESS_ENTRANCE/2026-09-30/address_entrance_36110.txt"
    assert sources.check_scope("ADDRESS_ENTRANCE", "36110") == "36"  # 원본 파일 이름의 코드도 받아요
    assert sources.check_scope("ADDRESS_ENTRANCE", "11000") == "11"
    assert len(sources.ADDRESS_SCOPES) == 16
    assert sources.headerless("ADDRESS_ENTRANCE") and not sources.headerless("STORES")


def test_region_boundary_keys():
    assert sources.s3_key("REGION_BOUNDARY_SIG", date(2026, 9, 30)) == "area/REGION_BOUNDARY_SIG/2026-09-30/boundary_sig.csv"
    assert sources.s3_key("REGION_BOUNDARY_EMD", date(2026, 9, 30), "ALL") == "area/REGION_BOUNDARY_EMD/2026-09-30/boundary_emd.csv"
    assert "REGION_BOUNDARY_RAW" not in sources.SOURCES


@pytest.mark.parametrize(
    "source,scope",
    [
        ("SUPERMARKET", "ALL"),  # 모르는 원천
        ("ADDRESS_ENTRANCE", None),  # 도로명주소는 시도 코드가 있어야 해요
        ("ADDRESS_ENTRANCE", "29"),  # 광주(29)는 전남광주(12)로 합쳐짐
        ("ADDRESS_ENTRANCE", "세종"),  # 이름이 아니라 코드
        ("STORES", None),  # 상가는 시도가 있어야 해요
        ("STORES", "광주"),  # 광주는 전남과 한 파일(전남광주)
        ("BUS_STOP", "서울"),  # 시설은 ALL만
        ("REGION_BOUNDARY_SIG", "11"),  # 경계는 전국 파일 하나라 ALL만
        ("REGION_BOUNDARY_RAW", "ALL"),  # 원본 zip은 보관만
    ],
)
def test_rejects_unknown_source_or_scope(source, scope):
    with pytest.raises(ValueError):
        sources.s3_key(source, date(2026, 6, 30), scope)


def test_keys_match_the_area_source_ready_contract():
    # contracts/events/area.source.ready.v1.json의 s3Key 패턴과 같아야 api가 받아요 (계약 파일에서 바로 읽음)
    import json
    import re
    from pathlib import Path

    schema = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "events" / "area.source.ready.v1.json").read_text(encoding="utf-8"))
    pattern = re.compile(schema["$defs"]["payload"]["properties"]["s3Key"]["pattern"])
    keys = [sources.s3_key(s, date(2026, 6, 30)) for s in sources.FILE_NAMES]
    keys += [sources.s3_key("STORES", date(2026, 6, 30), sido) for sido in sources.STORES_SCOPES]
    keys += [sources.s3_key("ADDRESS_ENTRANCE", date(2026, 9, 30), code) for code in sources.ADDRESS_SCOPES]
    assert all(pattern.match(k) for k in keys)
