"""LH 수집기 설정값. 바꿀 때는 이유를 주석으로 남겨요."""

API_KEY_ENV = "LH_API_KEY"  # 공공데이터포털 인증키 (LH API 3종 + 마이홈 API 활용신청)

LIST_URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"
DETAIL_URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeDtlInfo1/getLeaseNoticeDtlInfo1"
SUPPLY_URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeSplInfo1/getLeaseNoticeSplInfo1"
# 상세·공급정보 API는 목록 항목의 이 다섯 값이 모두 있어야 응답해요 (하나라도 빠지면 빈 응답)
DETAIL_KEYS = ("PAN_ID", "SPL_INF_TP_CD", "CCR_CNNT_SYS_DS_CD", "UPP_AIS_TP_CD", "AIS_TP_CD")
PAGE_SIZE = 100
MAX_LIST_PAGES = 20  # 마감 전 공고는 400건 안팎(4페이지). 응답이 이상해 끝없이 넘기는 일을 막는 상한
# 목록 API는 기간을 안 주면 최근 2개월 게시분만 줘요. 오래 열려 있는 상시모집을 놓치지 않게 3년 전부터 조회해요
LIST_LOOKBACK_DAYS = 365 * 3

# 마이홈포털 공공주택 모집공고 API (공공데이터포털 15108420). LH API에 없는 값(필지번호·나뉜 주소·금액 숫자)과
# LH가 '접수마감'으로 바꾼 상시모집 공고를 얻으려고 같이 써요
MYHOME_URL = "https://apis.data.go.kr/1613000/HWSPR02"
MYHOME_LISTS = {"rent": "rsdtRcritNtcList", "sale": "ltRsdtRcritNtcList"}  # 공공임대, 공공분양
MYHOME_PAGE_SIZE = 100
MYHOME_LH_ORG = "LH"  # 마이홈 목록에는 다른 기관 공고도 있어요. 지방 공사 공고는 각 게시판 수집기가 맡아서 LH 줄만 써요
MYHOME_CACHE_SECONDS = 30 * 60  # 한 회차 안에서는 마이홈 목록을 한 번만 받아요
# 마이홈에만 보이는 LH 공고를 LH 목록에서 다시 찾을 때: 공고명 단어 몇 개로, 단어마다 몇 페이지까지 찾을지
LOOKUP_KEYWORDS = 3
LOOKUP_MAX_PAGES = 3

API_HOST = "apis.data.go.kr"

# robots.txt가 금지하지만 팀 결정으로 요청하는 경로. 근거 없이 추가하지 않아요
ROBOTS_OVERRIDES = {
    "https://apply.lh.or.kr/lhapply/lhFile.do": (
        "팀 결정(2026-10-14): LH 상세정보 API가 알려주는 첨부 주소(AHFL_URL)로 공고문을 수집해요. "
        "매입임대 주택목록 엑셀(2026-10-15 추가)도 팀 결정으로 같은 주소에서 수집해요. "
        "청약플러스 robots.txt는 'User-agent: *' / 'Disallow: /lhapply/lhFile.do'"
    ),
}

# 사업공간(LH 상가) 공고 수집 여부. 역할 분담 C안은 상가를 포함하지만, 이벤트 계약(raw.notice.collected)이
# 아직 HOUSING만 받아서 지금은 주택만 수집해요
INCLUDE_BUSINESS = False
