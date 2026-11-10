"""정책 API 응답 예시. 필드 이름은 공식 명세(보조금24 Swagger)와 실제 응답 모양을 따랐어요. 값은 테스트용이에요."""

import json

GOV24_LIST = json.dumps(
    {
        "page": 1,
        "perPage": 500,
        "totalCount": 2,
        "currentCount": 2,
        "matchCount": 2,
        "data": [
            {
                "서비스ID": "000000465790",
                "서비스명": "청년 월세 한시 특별지원",
                "서비스목적요약": "청년층 주거비 부담 경감",
                "지원대상": "만 19~34세 부모와 별도 거주하는 무주택 청년",
                "선정기준": "청년가구 기준중위소득 60% 이하",
                "지원내용": "월 최대 20만원, 최장 12개월",
                "신청방법": "복지로 온라인 신청 또는 주민센터 방문",
                "신청기한": "2026. 12. 31.까지",
                "상세조회URL": "https://www.gov.kr/portal/rcvfvrSvc/dtlEx/000000465790",
                "소관기관명": "국토교통부",
                "소관기관유형": "중앙행정기관",
                "서비스분야": "주거·자립",
                "조회수": 15321,
                "등록일시": "20220822150443",
                "수정일시": "20260901093011",
            },
            {
                "서비스ID": "641000000123",
                "서비스명": "강남구 신혼부부 전세자금 대출이자 지원",
                "지원대상": "강남구 거주 신혼부부",
                "상세조회URL": "https://www.gov.kr/portal/rcvfvrSvc/dtlEx/641000000123",
                "소관기관명": "서울특별시 강남구",
                "소관기관유형": "시군구",
                "서비스분야": "주거·자립",
                "조회수": 88,
                "수정일시": "20260710120000",
            },
        ],
    },
    ensure_ascii=False,
)


def gov24_detail(service_id: str, required_docs: str = "신분증, 임대차계약서") -> str:
    return json.dumps(
        {
            "page": 1,
            "perPage": 1,
            "totalCount": 1,
            "data": [
                {
                    "서비스ID": service_id,
                    "구비서류": required_docs,
                    "온라인신청사이트URL": "https://www.bokjiro.go.kr",
                    "법령": "주거기본법",
                    "문의처": "마이홈콜센터 1600-1004",
                }
            ],
        },
        ensure_ascii=False,
    )


def gov24_conditions(service_id: str) -> str:
    return json.dumps(
        {"page": 1, "perPage": 1, "totalCount": 1, "data": [{"서비스ID": service_id, "JA0110": 19, "JA0111": 34, "JA0404": "Y", "JA0412": "Y", "JA0101": "N"}]},
        ensure_ascii=False,
    )


GOV24_KEY_ERROR = json.dumps({"code": -401, "msg": "등록되지 않은 인증키 입니다."}, ensure_ascii=False)

BOKJIRO_CENTRAL_LIST = """<?xml version="1.0" encoding="UTF-8"?>
<wantedList>
  <totalCount>1</totalCount><pageNo>1</pageNo><numOfRows>100</numOfRows>
  <resultCode>0</resultCode><resultMessage>SUCCESS</resultMessage>
  <servList>
    <servId>WLF00001188</servId>
    <servNm>청년 전세임대주택</servNm>
    <servDgst>청년에게 전세임대주택 지원</servDgst>
    <servDtlLink>https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?wlfareInfoId=WLF00001188&amp;wlfareInfoReldBztpCd=01</servDtlLink>
    <jurMnofNm>국토교통부</jurMnofNm>
    <intrsThemaArray>주거, 생활지원</intrsThemaArray>
    <inqNum>4021</inqNum>
  </servList>
</wantedList>"""

BOKJIRO_CENTRAL_DETAIL = """<?xml version="1.0" encoding="UTF-8"?>
<wantedDtl>
  <resultCode>0</resultCode><resultMessage>SUCCESS</resultMessage>
  <servId>WLF00001188</servId>
  <servNm>청년 전세임대주택</servNm>
  <tgtrDtlCn>무주택 청년(만 19~39세)</tgtrDtlCn>
  <slctCritCn><![CDATA[소득·자산 기준 충족]]></slctCritCn>
  <alwServCn>전세보증금 최대 1억 2천만원 지원</alwServCn>
  <basfrmList>
    <servSeCode>040</servSeCode>
    <servSeDetailLink>https://www.bokjiro.go.kr/files/form/청년전세임대_안내문.pdf</servSeDetailLink>
    <servSeDetailNm>청년전세임대 안내문</servSeDetailNm>
  </basfrmList>
  <basfrmList>
    <servSeCode>040</servSeCode>
    <servSeDetailLink>https://www.bokjiro.go.kr/files/form/download.do?id=77</servSeDetailLink>
    <servSeDetailNm>입주 신청서</servSeDetailNm>
  </basfrmList>
  <baslawList><servSeCode>030</servSeCode><servSeDetailNm>공공주택 특별법</servSeDetailNm></baslawList>
</wantedDtl>"""

BOKJIRO_LOCAL_LIST = """<?xml version="1.0" encoding="UTF-8"?>
<wantedList>
  <totalCount>1</totalCount><resultCode>0</resultCode>
  <servList>
    <servId>WLF00005123</servId>
    <servNm>연수구 청년 월세 지원</servNm>
    <ctpvNm>인천광역시</ctpvNm><sggNm>연수구</sggNm><bizChrDeptNm>청년정책과</bizChrDeptNm>
    <lastModYmd>20260903</lastModYmd>
    <intrsThemaNmArray>주거</intrsThemaNmArray>
    <inqNum>17</inqNum>
  </servList>
</wantedList>"""

BOKJIRO_LOCAL_DETAIL = """<?xml version="1.0" encoding="UTF-8"?>
<wantedDtl>
  <resultCode>0</resultCode>
  <servId>WLF00005123</servId>
  <servNm>연수구 청년 월세 지원</servNm>
  <sprtTrgtCn>연수구 거주 만 19~39세 무주택 청년</sprtTrgtCn>
  <alwServCn>월 20만원, 최대 10개월</alwServCn>
  <inqplHmpgReldList>
    <wlfareInfoDtlCd>020</wlfareInfoDtlCd>
    <wlfareInfoReldCn>https://www.yeonsu.go.kr/notice/view.do?id=901</wlfareInfoReldCn>
    <wlfareInfoReldNm>연수구청 공고</wlfareInfoReldNm>
  </inqplHmpgReldList>
</wantedDtl>"""

# 지자체 상세의 실제 모양 (2026-10-15 응답에서): 목록 태그 하위 이름이 중앙과 달라요
BOKJIRO_LOCAL_DETAIL_WITH_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<wantedDtl>
  <resultCode>0</resultCode><resultMessage>SUCCESS</resultMessage>
  <servId>WLF00006794</servId>
  <servNm>2026년 충청남도 청년 주택임차보증금 이자 지원사업</servNm>
  <ctpvNm>충청남도</ctpvNm>
  <bizChrDeptNm>충청남도 청년여성국 청년정책과</bizChrDeptNm>
  <lastModYmd>20261015</lastModYmd>
  <inqplHmpgReldList>
    <wlfareInfoDtlCd>020</wlfareInfoDtlCd>
    <wlfareInfoReldCn>http://www.chungnam.go.kr/cnnet/content.do?mnu_cd=CNNMENU02391</wlfareInfoReldCn>
    <wlfareInfoReldNm>충청남도 청년정책과</wlfareInfoReldNm>
  </inqplHmpgReldList>
  <basfrmList>
    <wlfareInfoDtlCd>040</wlfareInfoDtlCd>
    <wlfareInfoReldCn>https://www.bokjiro.go.kr/ssis-tbu/CmmFileUtil/siteQnaInfoDownload.do?atcflId=20261013UUWBM1731290211628410&amp;atcflSn=1</wlfareInfoReldCn>
    <wlfareInfoReldNm>★ 2026년 충청남도 청년 주택임차보증금 이자 지원사업 공고문 (1).hwpx</wlfareInfoReldNm>
  </basfrmList>
</wantedDtl>"""

DATA_GO_KR_KEY_ERROR = """<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>
<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"""


def youth_list(items: list[dict], total: int | None = None) -> str:
    return json.dumps(
        {"resultCode": 200, "resultMessage": "성공", "result": {"pagging": {"totCount": total if total is not None else len(items)}, "youthPolicyList": items}},
        ensure_ascii=False,
    )


YOUTH_POLICY = {
    "plcyNo": "20260815005400211234",
    "plcyNm": "인천 청년 월세 지원",
    "lclsfNm": "주거",
    "mclsfNm": "주거비 지원",
    "plcySprtCn": "월 최대 20만원",
    "sprtTrgtMinAge": "19",
    "sprtTrgtMaxAge": "39",
    "aplyYmd": "20260901 ~ 20261031",
    "aplyUrlAddr": "https://youth.incheon.go.kr/apply",
    "refUrlAddr1": "https://www.incheon.go.kr/board/view.do?id=3301",
    "refUrlAddr2": "",
    "zipCd": "2818500000,2817700000",
    "sprvsnInstCdNm": "인천광역시",
    "inqCnt": 120,
    "lastMdfcnDt": "2026-09-01 10:00:00",
}

ORIGIN_PAGE = """<html><body><div class="view">
  <p>2026년 인천 청년 월세 지원 사업 공고</p>
  <ul class="file">
    <li><a href="/cmm/fms/FileDown.do?atchFileId=F1&fileSn=0">2026년 청년월세지원 모집공고문.hwp (120KB)</a>
        <a href="/cmm/fms/preview.do?atchFileId=F1">미리보기</a></li>
    <li><a href="/cmm/fms/FileDown.do?atchFileId=F1&fileSn=1">신청서 서식.hwp</a></li>
    <li><a href="/cmm/fms/FileDown.do?atchFileId=F1&fileSn=2">선정자 명단.xlsx</a></li>
    <li><a href="https://www.incheon.go.kr/board/list.do">목록</a></li>
  </ul></div></body></html>"""


# 충남도청 게시판 모양: 본문을 감싼 틀에 'lnb'가 붙어 있고, 첨부 링크 글자는 '내려받기'뿐이에요
BOARD_PAGE = """<html><body><form id="frm">
<div class="gnb"><a href="/1">도정소식</a><a href="/2">분야별정보</a><a href="/3">참여소통</a><a href="/4">정보공개</a></div>
<div class="sub-layout lnb">
  <div class="lnb-menu"><a href="/a">농업정책 알림</a><a href="/b">공익직접지불제</a><a href="/c">청년농업인</a></div>
  <div class="board-view">
    <h3>「2026년 충청남도 청년농업인 지원정책」 한번에 알아보기</h3>
    <dl><dt>담당부서</dt><dd>농업정책과</dd><dt>등록일</dt><dd>2026-06-11</dd></dl>
    <ul class="file"><li>충청남도 청년농업인 지원정책(pdf) - 배포.pdf [3,345,415byte]
      <a href="/cnportal/cmmn/file/fileDown.do?atchFileId=abc&fileSn=1">내려받기</a> <a href="/cnportal/preview.do?id=abc">미리보기</a></li></ul>
    <div class="content">
      <p>□ 청년농업인 유입 및 정착 지원을 위한 「2026년 충청남도 청년농업인 지원정책」을 안내합니다.</p>
      <p>○ 지원대상: 도내 거주 만 18세 이상 45세 미만 청년농업인 (영농경력 10년 이하)</p>
      <p>○ 지원내용: 청년 농촌보금자리 조성(임대주택 20호), 영농정착지원금 월 최대 110만원(최장 3년), 스마트팜 창업 보육</p>
      <p>○ 신청방법: 주소지 시군 농업기술센터 방문 접수, 문의 041-635-4015</p>
    </div>
  </div>
</div>
<div id="footer"><a href="/p">개인정보처리방침</a><a href="/s">사이트맵</a> 충청남도 홍성군 홍북읍 충남대로 21</div>
</form></body></html>"""

# 사이트 첫 화면 모양: 글은 많지만 정책과 상관없는 소식 모음
HOME_PAGE = """<html><body><div class="main"><div class="news">
  <dl><dt>전주시청 청·장년 구인구직 만남의 날 행사 안내</dt>
  <dd>취업을 희망하는 청·장년 구직자 여러분! 다양한 기업의 채용 담당자를 직접 만나 면접 볼 수 있는 기회를 놓치지 마세요.
  일시: 2026년 10월 22일(목) 오후 2시, 장소: 전주시청 별관 1층 마주뜰, 참여기업 6개사 - 자동차 부품 생산·품질·보전, 냉동식품 생산·포장,
  식품 제조·포장, 물류 관리 등 다양한 직무에서 채용을 진행합니다. 현장 면접 후 바로 채용될 수 있으니 이력서를 지참해 주세요.</dd></dl>
</div></div></body></html>"""


# K-Startup 공고 (odcloud 모양). 값은 2026-10-18 실제 응답을 줄였어요
KSTARTUP_POLICY = {
    "id": 1,
    "pbanc_sn": 179540,
    "biz_pbanc_nm": "[ 모 집 ] GVC AI Platform &amp; Startup Enabling Program",
    "intg_pbanc_biz_nm": "AI 창업지원 프로그램",
    "intg_pbanc_yn": "N",
    "supt_biz_clsfc": "사업화",
    "supt_regin": "전국",
    "pbanc_ntrp_nm": "글로벌벤처센터",
    "sprv_inst": "민간",
    "pbanc_rcpt_bgng_dt": "20261016",
    "pbanc_rcpt_end_dt": "20261022",
    "rcrt_prgs_yn": "Y",
    "aply_trgt": "청소년,대학생,일반인,1인 창조기업",
    "aply_trgt_ctnt": "예비창업자 또는 창업 기업\r\nMVP 개발 및 서비스 출시를 목표로 하는 팀 또는 개인",
    "aply_excl_trgt_ctnt": None,
    "biz_enyy": "예비창업자,1년미만,3년미만",
    "biz_trgt_age": "만 20세 미만,만 20세 이상 ~ 만 39세 이하,만 40세 이상",
    "prfn_matr": None,
    "pbanc_ctnt": "AI 기반 플랫폼 서비스를 만들고 싶은 예비창업자와 초기 스타트업을 모집합니다.",
    "aply_mthd_onli_rcpt_istc": "https://global.venture.center/launchpad",
    "aply_mthd_vst_rcpt_istc": None,
    "biz_aply_url": None,
    "biz_gdnc_url": "global.venture.center/launchpad",
    "detl_pg_url": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=179540",
}


def kstartup_list(items: list[dict], total: int | None = None) -> str:
    n = len(items)
    return json.dumps(
        {"page": 1, "perPage": 1000, "totalCount": n if total is None else total, "currentCount": n, "matchCount": n, "data": items}, ensure_ascii=False
    )


# 기업마당 공고. 값은 2026-10-18 실제 응답을 줄였어요
BIZINFO_STARTUP = {
    "pblancId": "PBLN_000000000127001",
    "pblancNm": "[경북] 청도군 2026년 청년농업인 기술창업 지원사업 공고",
    "pblancUrl": "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127001",
    "jrsdInsttNm": "경상북도",
    "excInsttNm": "청도군",
    "pldirSportRealmLclasCodeNm": "창업",
    "pldirSportRealmMlsfcCodeNm": "사업화지원",
    "trgetNm": "창업벤처",
    "reqstBeginEndDe": "2026-10-16 ~ 2026-11-03",
    "reqstMthPapersCn": "방문 접수 - 청도군 농업기술센터",
    "bsnsSumryCn": "<p>청년농업인의 <b>기술창업</b>을 지원합니다.</p><p>☞&nbsp;1인당 최대 3천만원 지원</p><p>※ 자세한 지원대상 공고문 참조</p>",
    "hashtags": "창업,경북,청도군,청년농업인,2026",
    "printFileNm": "2026년 청년농업인 기술창업 지원사업 공고문.pdf",
    "printFlpthNm": "https://www.bizinfo.go.kr/cmm/fms/getImageFile.do?atchFileId=FILE_000000000700001&fileSn=0",
    "fileNm": "참가 신청서.hwp@공고문 원본.hwpx",
    "flpthNm": "https://www.bizinfo.go.kr/cmm/fms/getImageFile.do?atchFileId=FILE_000000000700002&fileSn=0@https://www.bizinfo.go.kr/cmm/fms/getImageFile.do?atchFileId=FILE_000000000700002&fileSn=1",
    "refrncNm": "청도군 농업기술센터 054-370-0000",
    "creatPnttm": "2026-10-16 14:04:07",
    "updtPnttm": "2026-10-16 15:23:38",
    "inqireCo": 3932,
    "totCnt": 2,
}
BIZINFO_SME = {
    **BIZINFO_STARTUP,
    "pblancId": "PBLN_000000000127291",
    "pblancNm": "[경남] 김해시 2026년 김해형 중소기업 근로소득 청년지원사업 모집 공고",
    "pldirSportRealmLclasCodeNm": "인력",
    "pldirSportRealmMlsfcCodeNm": "고용유지",
    "trgetNm": "중소기업",
    "hashtags": "인력,경남,김해시",
    "bsnsSumryCn": "<p>청년 1인당 360만원 근로소득 보전 지원금</p>",
}


def bizinfo_list(items: list[dict]) -> str:
    return json.dumps({"jsonArray": [{**item, "totCnt": len(items)} for item in items]}, ensure_ascii=False)
