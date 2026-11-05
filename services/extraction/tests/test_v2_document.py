"""V2 문서 모델·읽기 도구: 원문 글자 → 줄·표·행·칸 id, id → 원문 글자(인용이 원문과 늘 같음), 에이전트 도구가 실행 문맥에서 문서를 받음."""

import json

import pytest
from events import raw_event
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from test_pdf_reader import CELLS, attachment, make_pdf

from mujuthaek_extraction.intake import InMemorySourceReader, build_intake
from mujuthaek_extraction.v2.context import V2Context
from mujuthaek_extraction.v2.document import build, parse
from mujuthaek_extraction.v2.tools.read import READ_TOOLS

TEXT = "\n".join(
    [
        "공고 제목 줄",
        "--- 1쪽 ---",
        "1. 신청자격",
        "■ 소득 : 150% 이하",
        "[표 1-1]",
        "  [열 제목] 1. 구분 | 2. 보증금 | 3. -",
        "| 기준 | 14,202,000 | 105,200 |",
        "  ↳ 기준 — 보증금 14,202,000",
        "| 110%이하 | 15,622,000 |  |",
        "다음 본문",
        "--- 2쪽 ---",
        "2. 일정",
        "--- 1쪽 ---",
        "둘째 문서 줄",
        "[표 1-1]",
        "| a | b |",
        "=== 첨부 엑셀 목록.xlsx ===",
        "[엑셀 시트 공급]",
        "| 동 | 호 |",
        "| 101 | 1001 |",
        "=== 그림 판독 3쪽 ===",
        "| 1인 | 3,432,027 |",
        "판독 끝",
    ]
)


def test_ids_follow_pages_tables_rows_and_cells_and_point_back_to_the_exact_source():
    doc = parse(TEXT)
    assert [line.id for line in doc.lines] == ["p1.1", "p1.2", "p1.3", "p1.4", "p2.1", "d2.p1.1", "g1.1"]
    assert [table.id for table in doc.tables] == ["t1-1", "d2.t1-1", "x1.t1", "g1.t1"]
    first = doc.tables[0]
    assert first.columns == ("구분", "보증금", "") and len(first.lines) == 2  # 읽기 도움 줄(↳)은 원문이 아님
    assert doc.text("p1.3") == "■ 소득 : 150% 이하"
    assert doc.text("t1-1.r0") == "| 기준 | 14,202,000 | 105,200 |"
    assert doc.text("t1-1.r1.c1") == "15,622,000" and doc.text("t1-1.r1.c2") == ""
    assert doc.tables[2].caption == "공급" and doc.text("x1.t1.r1.c1") == "1001"
    # 인용 글은 id로 꺼내므로 원문에 그대로 있음(검증기의 원문 대조가 통과)
    pieces = [line.text for line in doc.lines] + [row for table in doc.tables for row in table.lines]
    pieces += [cell for table in doc.tables for row in table.rows for cell in row if cell]
    assert all(piece in TEXT for piece in pieces)
    with pytest.raises(KeyError):
        doc.text("t1-1.r9")
    assert not doc.exists("p9.1") and doc.exists("g1.t1.r0.c1")


def test_outline_view_and_search_show_small_pieces_with_ids():
    doc = parse(TEXT)
    outline = doc.outline()
    assert [h["id"] for h in outline["headings"]] == ["p1.2", "p1.3", "p2.1"]
    assert outline["tables"][0] == {"id": "t1-1", "area": "p1", "rows": 2, "columns": ["구분", "보증금", ""]}
    assert outline["tables"][1]["firstRow"] == ["a", "b"] and outline["tables"][2]["caption"] == "공급"
    assert doc.view_lines("p1.3", 3) == [
        {"id": "p1.3", "text": "■ 소득 : 150% 이하"},
        {"table": "t1-1", "rows": 2, "columns": ["구분", "보증금", ""]},
        {"id": "p1.4", "text": "다음 본문"},
    ]
    table = doc.view_table("t1-1", 0, 1)
    assert table["rows"] == [{"id": "t1-1.r0", "cells": ["기준", "14,202,000", "105,200"]}] and table["more"] is True
    hit = doc.search("14,202,000")[0]
    assert hit["id"] == "t1-1.r0" and hit["cell"] == "t1-1.r0.c1"
    assert doc.search("신청 자격")[0]["id"] == "p1.2"  # 공백은 무시
    near = doc.search("소득 150%이하")  # 똑같은 글자가 없으면 비슷한 줄
    assert near[0]["id"] == "p1.3" and near[0]["similarity"] >= 80


def test_document_from_a_real_pdf_keeps_v1_table_numbers():
    data = make_pdf(CELLS)
    event = raw_event()
    event["payload"]["files"] = [attachment("notice.pdf", data)]
    material = build_intake(event, InMemorySourceReader(files={"raw/x/notice.pdf": data})).material
    doc = build(material)
    table = next(t for t in doc.tables if t.id == "t1-1")
    assert all(doc.text(f"t1-1.r{r}") in material.text for r in range(len(table.lines)))
    assert doc.picture_pages == ()


class ToolCallingFake(GenericFakeChatModel):
    """녹화한 답(도구 호출 포함)을 차례로 내는 가짜 모델. create_agent가 도구를 묶을 수 있게 bind_tools는 그대로 돌려줍니다."""

    def bind_tools(self, tools, **kwargs):
        return self


def test_read_tools_take_the_document_from_the_agent_runtime_context():
    calls = AIMessage(
        content="",
        tool_calls=[
            {"name": "search", "args": {"query": "14,202,000"}, "id": "c1"},
            {"name": "view_table", "args": {"table": "t1-1", "start": 0, "count": 5}, "id": "c2"},
            {"name": "view_lines", "args": {"start": "p9.1", "count": 3}, "id": "c3"},
        ],
    )
    model = ToolCallingFake(messages=iter([calls, AIMessage(content="끝")]))
    agent = create_agent(model, tools=list(READ_TOOLS), context_schema=V2Context)
    result = agent.invoke({"messages": [HumanMessage("보증금 찾기")]}, context=V2Context(document=parse(TEXT)))
    tools = {m.tool_call_id: json.loads(m.content) for m in result["messages"] if m.type == "tool"}
    assert tools["c1"]["hits"][0]["cell"] == "t1-1.r0.c1"
    assert tools["c2"]["total"] == 2 and tools["c2"]["rows"][1]["id"] == "t1-1.r1"
    assert tools["c3"]["error"] == "UNKNOWN_ID"
    assert result["messages"][-1].content == "끝"
