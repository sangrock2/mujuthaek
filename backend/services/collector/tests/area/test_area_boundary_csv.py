"""구역의 도형 SHP → 경계 CSV. pyshp로 시험 SHP를 만들어 바꿔 봐요."""

import csv
from pathlib import Path

import pytest
import shapefile
from shapely import wkt

from mujuthaek_collector.area import boundary_csv

# 바깥 고리는 시계 방향, 구멍은 반시계 (SHP 규칙)
SQUARE = [(0, 0), (0, 100), (100, 100), (100, 0), (0, 0)]
HOLE = [(40, 40), (60, 40), (60, 60), (40, 60), (40, 40)]
FAR_SQUARE = [(1000, 0), (1000, 100), (1100, 100), (1100, 0), (1000, 0)]
BOWTIE = [(0, 0), (100, 100), (100, 0), (0, 100), (0, 0)]  # 꼬인 고리 — 잘못된 도형


def write_layer(folder: Path, layer: str, code_col: str, name_col: str, shapes: list[tuple[str, str, list]]):
    folder.mkdir(parents=True, exist_ok=True)
    with shapefile.Writer(str(folder / layer), shapeType=shapefile.POLYGON, encoding="cp949") as w:
        w.field(code_col, "C", size=10)
        w.field(name_col, "C", size=40)
        for code, name, rings in shapes:
            w.poly(rings)
            w.record(code, name)


def sido(root: Path, code: str, sig: list, emd: list):
    write_layer(root / code, "TL_SCCO_SIG", "SIG_CD", "SIG_KOR_NM", sig)
    write_layer(root / code, "TL_SCCO_EMD", "EMD_CD", "EMD_KOR_NM", emd)


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_converts_holes_parts_and_fixes_invalid_shapes(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    sido(
        src,
        "11000",
        sig=[("11110", "종로구", [SQUARE, HOLE]), ("11140", "중구", [SQUARE, FAR_SQUARE])],
        emd=[("11110101", "청운동", [SQUARE]), ("11110102", "신교동", [BOWTIE])],
    )

    summaries = boundary_csv.convert(str(src), str(out), sido_count=1)

    sig = read(out / "boundary_sig.csv")
    assert [r["code"] for r in sig] == ["11110", "11140"]
    assert sig[0]["name"] == "종로구"
    holed = wkt.loads(sig[0]["wkt"])
    assert holed.area == pytest.approx(100 * 100 - 20 * 20)  # 구멍만큼 빠짐
    assert not holed.contains(wkt.loads("POINT (50 50)"))
    two_parts = wkt.loads(sig[1]["wkt"])
    assert two_parts.geom_type == "MultiPolygon" and len(two_parts.geoms) == 2

    emd = read(out / "boundary_emd.csv")
    assert all(wkt.loads(r["wkt"]).is_valid for r in emd)
    assert summaries["boundary_emd.csv"].fixed == 1
    assert summaries["boundary_sig.csv"].rows == 2


def test_collects_every_sido_folder(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    sido(src, "11000", sig=[("11110", "종로구", [SQUARE])], emd=[("11110101", "청운동", [SQUARE])])
    sido(src, "36110", sig=[("36110", "세종특별자치시", [SQUARE])], emd=[("36110101", "반곡동", [SQUARE])])

    boundary_csv.convert(str(src), str(out), sido_count=2)

    assert [r["code"] for r in read(out / "boundary_sig.csv")] == ["11110", "36110"]
    with pytest.raises(ValueError, match="16개"):
        boundary_csv.convert(str(src), str(out))  # 진짜 자료는 시도 16개가 다 있어야 해요


@pytest.mark.parametrize(
    "sig,emd,message",
    [
        ([("1111", "짧은 코드", [SQUARE])], [("11110101", "청운동", [SQUARE])], "5자리"),
        ([("11110", "종로구", [SQUARE])], [("1111010", "일곱 자리", [SQUARE])], "8자리"),
        ([("11110", "종로구", [SQUARE]), ("11110", "또 종로구", [SQUARE])], [("11110101", "청운동", [SQUARE])], "두 번"),
    ],
)
def test_rejects_bad_or_duplicate_codes(tmp_path, sig, emd, message):
    sido(tmp_path / "src", "11000", sig=sig, emd=emd)
    with pytest.raises(ValueError, match=message):
        boundary_csv.convert(str(tmp_path / "src"), str(tmp_path / "out"), sido_count=1)


def test_main_prints_usage_and_failure(tmp_path, capsys):
    assert boundary_csv.main([]) == 2
    assert boundary_csv.main([str(tmp_path), str(tmp_path / "out")]) == 1
    assert "실패" in capsys.readouterr().err
