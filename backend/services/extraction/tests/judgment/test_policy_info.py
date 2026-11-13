"""정책 안내(policyInfo): 출처 API 칸(K-Startup · 기업마당)을 그대로 옮겨요. AI 값이 아니에요."""

from mujuthaek_extraction.publish import policy_info

KSTARTUP = {
    "supt_biz_clsfc": "시설ㆍ공간ㆍ보육",
    "pbanc_ctnt": "창업보육센터 신규 입주기업을 모집합니다.\r\n입주기업에는 최대 1,000만원 사업화 자금을 지원합니다.",
    "pbanc_ntrp_nm": "가상대학교 창업보육센터",
    "biz_prch_dprt_nm": "창업보육센터",
    "prch_cnpl_no": "0212345678",
    "aply_mthd_eml_rcpt_istc": "bi@example.ac.kr",
    "aply_mthd_onli_rcpt_istc": None,
    "biz_aply_url": None,
    "biz_gdnc_url": "bi.example.ac.kr/notice/1",
}

BIZINFO = {
    "pldirSportRealmLclasCodeNm": "창업",
    "pldirSportRealmMlsfcCodeNm": "창업공간지원",
    "bsnsSumryCn": "<p>청년 창업공간 입주자를 모집합니다.</p><p>☞ 창업공간(6개월) 지원</p>",
    "excInsttNm": "기초자치단체",
    "refrncNm": "가상군 청년팀 041-000-0000",
    "reqstMthPapersCn": "방문 접수\r\n- 접수처 : 가상군청",
}


def test_kstartup_fields_and_amount_phrase():
    info = policy_info({"sourceCode": "kstartup", "record": KSTARTUP})
    assert info["supportArea"] == "시설ㆍ공간ㆍ보육"
    assert info["organization"] == "가상대학교 창업보육센터"
    assert info["contact"] == "창업보육센터 0212345678"
    assert info["applyMethod"] == "이메일 bi@example.ac.kr"
    assert info["guideUrl"] == "https://bi.example.ac.kr/notice/1"  # scheme이 없으면 https를 붙여요
    assert info["applyUrl"] is None
    assert info["amountText"] == "최대 1,000만원"
    assert "\n" in info["summary"]


def test_bizinfo_fields_strip_html():
    info = policy_info({"sourceCode": "bizinfo", "record": BIZINFO})
    assert info["supportArea"] == "창업공간지원"
    assert info["summary"] == "청년 창업공간 입주자를 모집합니다.\n☞ 창업공간(6개월) 지원"
    assert info["contact"] == "가상군 청년팀 041-000-0000"
    assert info["applyMethod"].startswith("방문 접수")
    assert info["amountText"] is None


def test_other_sources_have_no_info():
    assert policy_info({"sourceCode": "youthcenter", "record": {"x": 1}}) is None
    assert policy_info({"sourceCode": "kstartup", "record": {}}) is None


def test_amount_written_in_thousands_reads_in_man_won_without_changing_the_value():
    from mujuthaek_extraction.publish import _readable_amount

    assert _readable_amount("최대 10,000천원") == "최대 1,000만원"  # 실측 2026-10-28 기업마당 서천 예비창업자 지원
    assert _readable_amount("최대 5,000 천 원") == "최대 500만원"
    assert _readable_amount("최대 1,005천원") == "최대 1,005천원"  # 나눠떨어지지 않으면 그대로
    assert _readable_amount("최대 3천만원") == "최대 3천만원"  # 천만 단위는 건드리지 않음
    assert _readable_amount("최대 1,000만원") == "최대 1,000만원"
