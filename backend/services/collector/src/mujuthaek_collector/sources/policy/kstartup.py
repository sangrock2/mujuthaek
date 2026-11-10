"""창업진흥원 K-Startup 지원사업 공고 (공공데이터포털 B552735 kisedKstartupService01). 중앙부처·지자체·민간의 창업지원 공고.

목록  https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01
        ?serviceKey=…&page=N&perPage=1000&returnType=json&cond[rcrt_prgs_yn::EQ]=Y
      {page, perPage, totalCount, currentCount, matchCount, data: [{pbanc_sn, biz_pbanc_nm, supt_biz_clsfc, supt_regin,
       pbanc_rcpt_bgng_dt, pbanc_rcpt_end_dt, aply_trgt, aply_trgt_ctnt, biz_enyy, biz_trgt_age, pbanc_ctnt, aply_mthd_*_istc,
       detl_pg_url, rcrt_prgs_yn …}]}
상세  목록 한 건에 공고 항목이 다 있어서 따로 부르지 않아요.
모집  모집 중(rcrt_prgs_yn=Y)인 공고만 받아요 (2026-10-18 228건, 1번 호출). 전체는 2021년부터 30,373건(31번, 53MB)이고,
      모집 여부와 접수 기간이 어긋난 공고는 없었어요. 마감된 공고는 목록에서 빠지고, 저장한 버전은 그대로 남아요.
거름  창업 공간·지원금·정책자금만 (base.startup_in_scope). 지원 분야 '시설ㆍ공간ㆍ보육'·'사업화'·'융자ㆍ보증'·'정책자금'이면 넣되,
      이름에 교육·행사 단어가 있으면 빼요. 다른 분야(교육·멘토링·행사·판로·글로벌·R&D·인력)도 이름에 공간·자금 단어가 있으면 넣어요.
      2026-10-18 모집 중 228건 중 82건. 나머지는 SKIPPED로 남겨요.
첨부  API에 첨부가 없어요. 첨부 파일(/afile/…)은 robots.txt 'Disallow: /afile*/'라 받지 않아요.
원문  사업공간 모집(SPACE_RECRUITMENT)만 상세 화면(detl_pg_url)의 본문을 읽어요 (2026-10-22 결정). API 요약에는 없는
      '입주공간 및 이용료'(호실별 면적, ㎡당 이용료, 입주 기간, 모집 규모)가 본문에 있어서예요. 지원금·정책자금 공고는 열지 않아요.
      robots.txt의 'Disallow: /bizpbanc-ongoing.do'는 사이트 맨 앞 경로라 '/web/contents/bizpbanc-ongoing.do'는 허용이에요
      (기관 의도와 어긋날 수 있어 팀에서 정했어요). 하루 최대 수십 건, 4초 간격, 내용이 바뀔 때만 다시 열어요.
수정일 목록에 수정일이 없어서 목록 항목 해시로 바뀐 것을 봐요.
"""

from __future__ import annotations

import html
from typing import Any

from mujuthaek_collector.sources.base import Request
from mujuthaek_collector.sources.policy.base import (
    NATIONWIDE,
    SIDO,
    SPACE_RECRUITMENT,
    UNKNOWN,
    PolicyDetail,
    PolicyItem,
    PolicyPage,
    PolicySource,
    build_url,
    clean,
    split_names,
    startup_in_scope,
)
from mujuthaek_collector.sources.policy.gov24 import read_data

API = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"

LABELS = {
    "pbanc_sn": "공고 일련번호",
    "biz_pbanc_nm": "지원사업 공고명",
    "intg_pbanc_biz_nm": "통합 공고 사업명",
    "intg_pbanc_yn": "통합 공고 여부",
    "supt_biz_clsfc": "지원 분야",
    "supt_regin": "지역",
    "pbanc_ntrp_nm": "창업 지원 기관",
    "sprv_inst": "주관 기관 구분",
    "biz_prch_dprt_nm": "담당 부서",
    "prch_cnpl_no": "담당자 연락처",
    "pbanc_rcpt_bgng_dt": "접수 시작일",
    "pbanc_rcpt_end_dt": "접수 종료일",
    "rcrt_prgs_yn": "모집 진행 여부",
    "aply_trgt": "신청 대상",
    "aply_trgt_ctnt": "신청 대상 내용",
    "aply_excl_trgt_ctnt": "신청 제외 대상",
    "biz_enyy": "창업 기간",
    "biz_trgt_age": "대상 연령",
    "prfn_matr": "우대 사항",
    "pbanc_ctnt": "공고 내용",
    "aply_mthd_onli_rcpt_istc": "온라인 접수 방법",
    "aply_mthd_vst_rcpt_istc": "방문 접수 방법",
    "aply_mthd_pssr_rcpt_istc": "우편 접수 방법",
    "aply_mthd_fax_rcpt_istc": "팩스 접수 방법",
    "aply_mthd_eml_rcpt_istc": "이메일 접수 방법",
    "aply_mthd_etc_istc": "기타 접수 방법",
    "biz_gdnc_url": "사업 안내 주소",
    "biz_aply_url": "공고 상세 주소",
    "detl_pg_url": "K-Startup 공고 주소",
}
IN_SCOPE_FIELDS = {"시설ㆍ공간ㆍ보육", "사업화", "융자ㆍ보증", "정책자금"}  # 창업 공간·지원금·정책자금
APPLY_METHODS = {
    "aply_mthd_onli_rcpt_istc": "온라인",
    "aply_mthd_vst_rcpt_istc": "방문",
    "aply_mthd_pssr_rcpt_istc": "우편",
    "aply_mthd_fax_rcpt_istc": "팩스",
    "aply_mthd_eml_rcpt_istc": "이메일",
    "aply_mthd_etc_istc": "기타",
}


def unescaped(value: Any) -> Any:
    """'기술개발(R&amp;D)'처럼 HTML 문자 참조가 섞여 와요."""
    value = clean(value)
    return html.unescape(value) if isinstance(value, str) else value


def apply_period(record: dict[str, Any]) -> str | None:
    start, end = record.get("pbanc_rcpt_bgng_dt"), record.get("pbanc_rcpt_end_dt")
    return f"{start or ''} ~ {end or ''}" if start or end else None


def how_to_apply(record: dict[str, Any]) -> str | None:
    lines = [f"{label}: {record[key]}" for key, label in APPLY_METHODS.items() if record.get(key)]
    return "\n".join(lines) or None


def apply_url(record: dict[str, Any]) -> str | None:
    """공고 상세 주소, 없으면 온라인 접수 설명이 주소일 때 그 주소."""
    for key in ("biz_aply_url", "aply_mthd_onli_rcpt_istc"):
        value = str(record.get(key) or "").strip()
        if value.startswith("http"):
            return value
    return None


def target(record: dict[str, Any]) -> str | None:
    """신청 대상 글 + 쉼표 목록 칸(대상, 창업 기간, 연령). 연령은 세 구간이 다 있으면 제한 없음이지만 그대로 둬요 (판단은 AI)."""
    parts = [
        record.get("aply_trgt_ctnt"),
        *(f"{LABELS[k]}: {record[k]}" for k in ("aply_trgt", "biz_enyy", "biz_trgt_age") if record.get(k)),
    ]
    return "\n".join(p for p in parts if p) or None


def criteria(record: dict[str, Any]) -> str | None:
    parts = [f"{LABELS[k]}: {record[k]}" for k in ("aply_excl_trgt_ctnt", "prfn_matr") if record.get(k)]
    return "\n".join(parts) or None


def region_of(value: Any) -> tuple[str, list[str]]:
    """supt_regin '전국' 또는 시도 이름('서울', '경기'). 여러 개면 쉼표로 와요."""
    names = split_names(value)
    if not names:
        return UNKNOWN, []
    if "전국" in names:
        return NATIONWIDE, []
    return SIDO, names


class KStartupSource(PolicySource):
    code = "kstartup"
    name = "K-Startup 창업지원사업 공고"
    provider = "KSTARTUP"
    listed_keys = ("pbanc_rcpt_bgng_dt",)  # 등록일 (처음 수집 개수 제한)
    field = "STARTUP_SUPPORT"
    page_size = 1000
    origin_files = False  # 상세 화면의 첨부(/afile/)는 robots.txt 금지라 본문 글자만 읽어요
    key_env = "DATA_GO_KR_SERVICE_KEY"
    labels = LABELS
    ai_keys = (
        "biz_pbanc_nm", "intg_pbanc_biz_nm", "supt_biz_clsfc", "supt_regin", "aply_trgt", "aply_trgt_ctnt", "aply_excl_trgt_ctnt",
        "biz_enyy", "biz_trgt_age", "prfn_matr", "pbanc_ctnt", "pbanc_rcpt_bgng_dt", "pbanc_rcpt_end_dt",
        "aply_mthd_onli_rcpt_istc", "aply_mthd_vst_rcpt_istc", "aply_mthd_pssr_rcpt_istc", "aply_mthd_eml_rcpt_istc", "aply_mthd_etc_istc",
    )  # fmt: skip

    def list_request(self, page: int, segment: str | None = None) -> Request:
        params = {"serviceKey": self.api_key, "page": page, "perPage": self.page_size, "returnType": "json", "cond[rcrt_prgs_yn::EQ]": "Y"}
        return Request(build_url(API, params))

    def parse_list(self, body: str) -> PolicyPage:
        data = read_data(body, "K-Startup 공고 목록")  # 보조금24와 같은 odcloud 모양·오류
        items = []
        for row in data.get("data") or []:
            record = {k: unescaped(v) for k, v in row.items() if k != "id"}  # id는 응답 안의 순번이라 매번 바뀌어요
            policy_id = record.get("pbanc_sn")
            if policy_id in (None, ""):
                continue
            items.append(PolicyItem(str(policy_id), record.get("biz_pbanc_nm") or str(policy_id), self.record_marker(record), record))
        return PolicyPage(items, data.get("totalCount"), len(data.get("data") or []))

    def wanted(self, item: PolicyItem) -> bool:
        return startup_in_scope(item.title, category_ok=item.record.get("supt_biz_clsfc") in IN_SCOPE_FIELDS)

    def body_text(self, record: dict[str, Any]) -> str:
        """응답의 항목 순서가 뒤섞여 와서 LABELS 순서(공고명 → 대상 → 내용 → 신청 방법)로 맞춰요."""
        order = {key: i for i, key in enumerate(LABELS)}
        return super().body_text(dict(sorted(record.items(), key=lambda kv: order.get(kv[0], len(order)))))

    def parse_detail(self, item: PolicyItem, bodies: list[str]) -> PolicyDetail:
        record = dict(item.record)
        scope, names = region_of(record.get("supt_regin"))
        detail_url = record.get("detl_pg_url")
        space = self.classify(item.title, record) == SPACE_RECRUITMENT and str(detail_url or "").startswith("http")
        return PolicyDetail(
            record=record,
            origin_urls=[detail_url] if space else [],  # 사업공간 모집만 상세 화면 본문을 읽어요
            detail_url=detail_url,
            apply_url=apply_url(record),
            agency=record.get("pbanc_ntrp_nm"),
            region_scope=scope,
            region_names=names,
            categories=split_names(record.get("supt_biz_clsfc")),
            summary=record.get("intg_pbanc_biz_nm"),
            target=target(record),
            criteria=criteria(record),
            benefit=record.get("pbanc_ctnt"),
            how_to_apply=how_to_apply(record),
            apply_period=apply_period(record),
        )
