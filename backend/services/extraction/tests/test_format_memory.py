"""기관 기억(V2 6단계) 그림자 모드: 같은 기관의 같은 모양 공급표 열 해석을 기억해 두고, 새 해석과 같은지만 기록합니다(쓰지 않음)."""

import json
from dataclasses import replace

from test_supply_tables import MAPPING, column, material, structure_answer

from mujuthaek_extraction import format_memory
from mujuthaek_extraction import supply_tables as st
from mujuthaek_extraction.extract import run_extraction
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.rules.housing_notice import RULES


def table(label, titles=("단지명", "모집 세대수")):
    return st.Table(label, 1, "모집 현황", titles, (titles, ("동삼2", "300")), ((0, 1), (2, 3)))


def reading(label, kind="OFFERED", complex_name=None):
    columns = [column(1, "COMPLEX"), column(2, "COUNT", ck=kind)]
    return {"tables": [{"table": label, "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": complex_name, "columns": columns}]}


def test_the_memory_only_records_whether_a_new_reading_matches_the_remembered_one(monkeypatch, tmp_path):
    assert format_memory.observe("bmc", ([table("1-1")], reading("1-1"))) is None  # 설정이 없으면 꺼짐
    monkeypatch.setenv(format_memory.ENV, str(tmp_path))
    assert format_memory.observe("bmc", ([table("1-1")], reading("1-1"))) == {"tables": 1, "remembered": 0, "same": 0, "changed": []}
    # 다른 공고의 같은 모양 표: 표 번호·단지 이름은 공고마다 달라도 해석이 같으면 일치
    assert format_memory.observe("bmc", ([table("3-2")], reading("3-2", complex_name="다대4"))) == {"tables": 1, "remembered": 1, "same": 1, "changed": []}
    assert format_memory.observe("bmc", ([table("2-1")], reading("2-1", kind="TOTAL_HOUSING"))) == {
        "tables": 1,
        "remembered": 1,
        "same": 0,
        "changed": ["2-1"],
    }
    assert format_memory.observe("sh", ([table("1-1")], reading("1-1")))["remembered"] == 0  # 기관마다 따로
    assert format_memory.observe("bmc", ([table("1-1", ("단지명", "모집세대수 "))], reading("1-1")))["remembered"] == 1  # 띄어쓰기만 다르면 같은 모양
    assert format_memory.observe("bmc", ([table("1-1", ("단지", "모집 세대수"))], reading("1-1")))["remembered"] == 0  # 열 제목이 다르면 새 모양
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bmc.json", "sh.json"]


def test_the_extraction_run_keeps_the_table_reading_it_used():
    source = material()
    model = RecordedModel({"supply_tables": [json.dumps(MAPPING)], "structure": [structure_answer(source)]})
    rules = replace(RULES, calls=RULES.calls[:1], split_calls=(), large_text_chars=None)
    tables, answered = run_extraction(rules, source, model).table_mapping
    assert [t.label for t in tables] == ["1-1"] and answered == MAPPING
