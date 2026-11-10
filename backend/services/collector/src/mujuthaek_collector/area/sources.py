"""area 원천 9종과 S3 키 규칙.

S3 키: area/{원천}/{기준일}/{영문 파일 이름}.csv  (예: area/STORES/2026-06-30/stores_gangwon.csv)
상가정보는 시도 파일 하나가 적재 한 번이라 범위(scope)가 시도 이름이고, 나머지는 ALL이에요.
도로명주소 출입구는 시도 파일마다 범위가 시도 코드 두 자리(11, 36 …)이고, 원본 그대로 .txt로 올려요
(예: area/ADDRESS_ENTRANCE/2026-09-30/address_entrance_36110.txt).
구역 경계(REGION_BOUNDARY_SIG·EMD)는 구역의 도형 SHP를 전국 CSV 하나씩으로 바꿔(boundary_csv.py) 올려요. 원본 zip은
REGION_BOUNDARY_RAW로 같이 보관하지만 적재 대상이 아니라 이벤트를 만들지 않아요.
파일 이름을 영문으로 두는 건 LANG이 없는 서버·컨테이너에서도 키를 그대로 다룰 수 있게 하려는 거예요.
"""

from datetime import date

ALL = "ALL"

# 원천 → 영문 파일 이름 (상가는 시도마다 따로라 STORES_SCOPES로)
FILE_NAMES = {
    "SUBWAY_STATION": "subway_station",
    "BUS_STOP": "bus_stop",
    "SCHOOL": "school",
    "PARK": "park",
    "HOSPITAL": "hospital",
    "REGION_BOUNDARY_SIG": "boundary_sig",
    "REGION_BOUNDARY_EMD": "boundary_emd",
}
STORES = "STORES"
ADDRESS_ENTRANCE = "ADDRESS_ENTRANCE"
SOURCES = (*FILE_NAMES, STORES, ADDRESS_ENTRANCE)
# S3에 보관만 하는 원본 (목록에 있어도 적재 요청을 만들지 않아요)
ARCHIVE_ONLY = frozenset({"REGION_BOUNDARY_RAW"})

# 상가(상권)정보 시도 파일 이름의 시도 → 영문 이름 (소상공인시장진흥공단 2026-06 기준 16개. 광주는 전남과 한 파일)
STORES_SCOPES = {
    "강원": "gangwon",
    "경기": "gyeonggi",
    "경남": "gyeongnam",
    "경북": "gyeongbuk",
    "대구": "daegu",
    "대전": "daejeon",
    "부산": "busan",
    "서울": "seoul",
    "세종": "sejong",
    "울산": "ulsan",
    "인천": "incheon",
    "전남광주": "jeonnam_gwangju",
    "전북": "jeonbuk",
    "제주": "jeju",
    "충남": "chungnam",
    "충북": "chungbuk",
}


# 도로명주소 출입구(주소기반산업지원서비스, 2026-10 기준 16개) 범위 = 시도 코드 두 자리 → 원본 파일 이름의 시도 코드
# (RNENTDATA_2610_{코드}.txt. 12는 전남광주 통합특별시 새 코드, 세종만 36110)
ADDRESS_SCOPES = {
    "11": "11000",
    "12": "12000",
    "26": "26000",
    "27": "27000",
    "28": "28000",
    "30": "30000",
    "31": "31000",
    "36": "36110",
    "41": "41000",
    "43": "43000",
    "44": "44000",
    "47": "47000",
    "48": "48000",
    "50": "50000",
    "51": "51000",
    "52": "52000",
}


def check_scope(source: str, scope: str | None) -> str:
    """원천과 범위가 맞는지 보고 범위를 돌려줘요. 상가는 시도 이름, 도로명주소는 시도 코드 두 자리
    (원본 파일의 다섯 자리 코드 36110도 받아요), 나머지는 ALL(비우면 ALL)."""
    if source not in SOURCES:
        raise ValueError(f"모르는 area 원천이에요: {source} (가능: {', '.join(SOURCES)})")
    if source == ADDRESS_ENTRANCE:
        for short, code in ADDRESS_SCOPES.items():
            if scope in (short, code):
                return short
        raise ValueError(f"도로명주소는 시도 코드가 있어야 해요: {scope} (가능: {', '.join(ADDRESS_SCOPES)})")
    if source == STORES:
        if scope not in STORES_SCOPES:
            raise ValueError(f"상가정보는 시도 이름이 있어야 해요: {scope} (가능: {', '.join(STORES_SCOPES)})")
        return scope
    if scope not in (None, "", ALL):
        raise ValueError(f"{source}는 범위가 ALL이에요: {scope}")
    return ALL


def file_name(source: str, scope: str | None = None) -> str:
    scope = check_scope(source, scope)
    if source == ADDRESS_ENTRANCE:
        return f"address_entrance_{ADDRESS_SCOPES[scope]}.txt"
    base = f"stores_{STORES_SCOPES[scope]}" if source == STORES else FILE_NAMES[source]
    return base + ".csv"


def headerless(source: str) -> bool:
    """머리줄 없는 원천 (줄 수를 셀 때 머리줄을 빼지 않아요)."""
    return source == ADDRESS_ENTRANCE


def s3_key(source: str, data_date: date, scope: str | None = None) -> str:
    return f"area/{source}/{data_date.isoformat()}/{file_name(source, scope)}"
