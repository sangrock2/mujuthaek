"""문의처 코드 보충(assemble/contacts): 원문 문의처 줄의 번호가 안내에 없으면 AI 출력과 같은 모양으로 덧붙입니다. 유료 호출 없음."""

from mujuthaek_extraction.assemble.contacts import fill_contacts, missing_contacts

TEXT = "\n".join(
    [
        "| 임대문의 | ◦문의처 : 051-810-9905~8 ◦공고문 : 부산도시공사 홈페이지 |",
        "■ 문의전화는 안양 냉천지구 공공임대주택 공급상담실(031-466-0188)로 가능합니다.",
        "문의 시 본인 휴대전화(010-1234-5678)를 확인합니다.",  # 휴대전화는 보지 않음
        "임대료 납부 계좌 : 123-456-7890",  # 문의 낱말이 없는 줄
    ]
)


def schedules_part(guidance):
    return {"quotes": [{"ref": "q1", "documentId": "pdf-text", "text": "가상"}], "schedules": [], "guidance": guidance}


def contact(phone):
    return {"id": "c1", "kind": "CONTACT", "title": "공급상담실", "description": "문의처예요.", "scope": {}, "phone": phone, "url": None, "quoteRefs": ["q1"]}


def test_contact_line_missing_from_the_guidance_is_added_with_its_source_quote():
    # 2026-11-09 23건 bmc-75: 공고 끝 「| 임대문의 | ◦문의처 : 051-810-9905~8 … |」를 일정·안내 담당이 넣지 않아 문의처가 없었음
    structure, part = {"quotes": [], "notice": {}}, schedules_part([contact("031-466-0188")])
    filled = fill_contacts([structure, part], TEXT, "pdf-text")
    assert filled[0] is structure and part["guidance"] == [contact("031-466-0188")]  # 다른 조각과 원래 조각은 그대로
    [added] = [g for g in filled[1]["guidance"] if g["id"].startswith("contact-code-")]
    assert (added["kind"], added["title"], added["phone"]) == ("CONTACT", "임대문의", "051-810-9905~8")
    [quote] = [q for q in filled[1]["quotes"] if q["ref"] == added["quoteRefs"][0]]
    assert quote["text"] == "임대문의 | ◦문의처 : 051-810-9905~8" and quote["text"] in TEXT  # 원문 그대로라 인용 검증을 지남
    assert added["scope"]["level"] == "NOTICE" and added["description"] == "임대문의 전화번호예요."


def test_numbers_already_in_the_guidance_mobile_numbers_and_parts_without_guidance_are_left_alone():
    assert [phone for _, phone, _ in missing_contacts([contact("051-810-9905"), contact("031-466-0188")], TEXT)] == []  # 범위 끝 번호는 떼고 견줌
    assert [phone for _, phone, _ in missing_contacts([], TEXT)] == ["051-810-9905~8", "031-466-0188"]
    parts = [{"quotes": [], "eligibility": []}]
    assert fill_contacts(parts, TEXT, "pdf-text") is parts
    picture = "=== 그림 판독 공고.pdf 1쪽 ===\n문의처 : 02-1234-5678"  # 그림 판독 글은 보지 않음
    assert missing_contacts([], picture) == []


def test_fax_numbers_on_a_contact_line_are_not_added_as_phone_numbers():
    # 2026-11-10 코드 검토: 문의처 줄에 함께 적힌 팩스 번호도 「문의처 전화번호예요」로 게시됐음
    text = "\n".join(
        [
            "◦ 문의처 : 051-810-9905~8 (팩스 : 051-810-9909)",
            "| 임대문의 | 주택관리팀 02-123-4567, FAX 02-123-4599 |",
            "문의 T. 031-111-2222 F. 031-111-2299",
        ]
    )
    assert [phone for _, phone, _ in missing_contacts([], text)] == ["051-810-9905~8", "02-123-4567", "031-111-2222"]


def test_fax_in_parentheses_or_with_a_particle_is_skipped_but_english_words_ending_in_f_are_not_fax():
    # 2026-11-10 재검토: 「팩스(02-…)」「팩스번호는 02-…」는 팩스로 못 보고, 「청년주거TF 02-…」「T/F」「Staff」의 전화번호는 뺐음
    text = "\n".join(
        [
            "문의처 02-123-4567 팩스(02-765-4321)",
            "문의 02-123-4568, FAX(02-765-4322)",
            "문의 02-123-4569, 팩스번호는 02-765-4323",
            "문의 청년주거TF 02-555-1234",
            "문의 T/F 02-555-1235",
            "문의 Staff 02-555-1236",
        ]
    )
    phones = [phone for _, phone, _ in missing_contacts([], text)]
    assert phones == ["02-123-4567", "02-123-4568", "02-123-4569", "02-555-1234", "02-555-1235", "02-555-1236"]
