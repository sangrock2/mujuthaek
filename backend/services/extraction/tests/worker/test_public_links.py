"""화면 링크(정책 원문·신청·안내 주소)는 http(s) 공개 주소만 (2026-11-16 보안 감사 L-4). 합성 값만 씁니다. 네트워크·AI 호출 없음.

collector가 수집할 때 거르고(collector core/links.py), extraction이 같은 규칙(links.public_link)으로 한 번 더 걸러요.
계약(policy.extracted source.detailUrl·applyUrl, extraction.completed detailUrl·policyInfo.applyUrl·guideUrl)도 같은 패턴을 강제해요."""

import copy
import json
import logging
import uuid
from contextlib import contextmanager

import pytest
from jsonschema import Draft202012Validator

from mujuthaek_extraction.benefit.build import build_payload
from mujuthaek_extraction.benefit.codes import rules_for
from mujuthaek_extraction.benefit.reading import BenefitReading
from mujuthaek_extraction.contracts import contracts_dir, tools
from mujuthaek_extraction.links import MAX_LINK_CHARS, public_link
from mujuthaek_extraction.publish import policy_detail_url, policy_info
from mujuthaek_extraction.review_api import ReviewService
from mujuthaek_platform.events import new_event
from tests.worker.test_benefit import REGIONS, answer, payload

BENEFIT_SCHEMA = "events/policy.extracted.v1.json"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://www.youthcenter.go.kr/youthPolicy/1", "https://www.youthcenter.go.kr/youthPolicy/1"),
        (" HTTP://Apply.Example.go.kr/A?b=1 ", "http://Apply.Example.go.kr/A?b=1"),
        ("www.housing.example/apply", "https://www.housing.example/apply"),
        ("https://www.gov.kr/공고/1", "https://www.gov.kr/공고/1"),
    ],
)
def test_public_links_are_kept_with_a_lowercase_scheme(value, expected):
    assert public_link(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "없음",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "intent://scan/#Intent;scheme=zxing;end",
        "search-ms:query=x",
        "//evil.example/a",
        "https:/evil.example",
        "https://user:pw@example.go.kr/",
        "https://good.go.kr\\@evil.example/",
        "https://example.go.kr/a b",
        "https://example.go.kr/‮gnp.exe",
        "http://127.0.0.1/",
        "http://2130706433/",
        "http://localhost/",
        "https://example.go.kr:abc/",
        "https://example.go.kr/" + "a" * MAX_LINK_CHARS,
    ],
)
def test_other_values_are_not_links(value):
    assert public_link(value) is None


def built(**changes):
    data = payload(**changes)
    reading = BenefitReading(answer(), truncated=False, model="recorded")
    return build_payload(data, reading, rules_for("youth", data["record"], data["text"]), REGIONS)


def test_benefit_links_are_checked_again_before_the_contract(caplog):
    with caplog.at_level(logging.WARNING, logger="mujuthaek_extraction.benefit.build"):
        extracted = built(detailUrl="javascript:alert(document.cookie)", applyUrl="www.housing.example/apply")
    assert extracted["source"]["detailUrl"] is None and extracted["source"]["applyUrl"] == "https://www.housing.example/apply"
    assert [r.field for r in caplog.records] == ["detailUrl"] and "javascript" not in caplog.text  # 주소 자체는 로그에 남기지 않아요
    event = new_event("policy.extracted", "extraction", extracted)
    assert tools().validate(event, BENEFIT_SCHEMA) == []
    # 계약도 http(s) 공개 주소만 받아요(api가 받을 때 같은 스키마로 검사해요)
    for bad in ("javascript:alert(1)", "www.housing.example/apply", "https://user@evil.example/", "https://a.example/b c", "HTTPS://a.example"):
        broken = copy.deepcopy(event)
        broken["payload"]["source"]["applyUrl"] = bad
        assert tools().validate(broken, BENEFIT_SCHEMA), bad


def test_policy_judgment_links_are_public_http_and_match_the_contract():
    record = {"pbanc_ctnt": "창업 공간 입주기업 모집", "biz_aply_url": "HTTPS://Apply.Example.ac.kr/x", "biz_gdnc_url": "https://user:pw@evil.example/"}
    info = policy_info({"sourceCode": "kstartup", "record": record})
    assert info["applyUrl"] == "https://Apply.Example.ac.kr/x" and info["guideUrl"] is None
    assert policy_detail_url({"detailUrl": "HTTP://www.k-startup.go.kr/a"}) == "http://www.k-startup.go.kr/a"
    assert policy_detail_url({"detailUrl": "http://192.168.0.10/admin"}) is None
    schema = json.loads((contracts_dir() / "events" / "extraction.completed.v1.json").read_text(encoding="utf-8"))
    fields = schema["$defs"]["payload"]["properties"]
    for field in (fields["detailUrl"], fields["policyInfo"]["properties"]["applyUrl"], fields["policyInfo"]["properties"]["guideUrl"]):
        check = Draft202012Validator(field)
        assert check.is_valid(None) and check.is_valid(info["applyUrl"])
        assert not check.is_valid("javascript:alert(1)") and not check.is_valid("https://user@evil.example/")


class FakeBenefitStore:
    def __init__(self, stored):
        self.stored = stored
        self.decided = []

    def benefit_review(self, review_id):
        return {"reviewStatus": "PENDING", "payload": copy.deepcopy(self.stored)}

    def decide_benefit(self, review_id, decision, event, note, reviewer, edits):
        self.decided.append(event)


def test_benefit_approval_cleans_links_saved_before_the_check():
    # 검사 전에 쌓인 결과: source는 잠근 칸이라 검수자가 고칠 수 없어, 그대로면 승인할 때 새 계약 패턴에 걸려요
    stored = built()
    stored["source"] |= {"detailUrl": "javascript:alert(1)", "applyUrl": "www.housing.example/apply"}
    store = FakeBenefitStore(stored)

    @contextmanager
    def session():
        yield store

    service = ReviewService(session, lambda kind, producer, body: {**new_event(kind, producer, body), "eventId": str(uuid.uuid4())})
    status, body = service.benefit_decide("r-1", "APPROVED", {})
    assert status == 200, body
    [event] = store.decided
    assert event["payload"]["source"]["detailUrl"] is None
    assert event["payload"]["source"]["applyUrl"] == "https://www.housing.example/apply"
    assert tools().validate(event, BENEFIT_SCHEMA) == []
