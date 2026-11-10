"""구역의 도형(SHP) → 경계 CSV. 시군구(TL_SCCO_SIG)와 법정읍면동(TL_SCCO_EMD)만 써요.

쓰는 법:  uv run --group boundary python -m mujuthaek_collector.area.boundary_csv <juso_boundary 폴더> <출력 폴더>
입력: 시도 코드 이름 폴더(11000, 12000 …) 안의 TL_SCCO_SIG.shp, TL_SCCO_EMD.shp (CP949, .prj 없음, UTM-K EPSG:5179)
출력: boundary_sig.csv, boundary_emd.csv — 칸 code, name, wkt (좌표는 UTM-K 그대로, 경위도로 바꾸기는 api가 적재할 때 ST_Transform으로)

여러 조각·구멍은 GeoJSON 규칙(바깥 고리 시계 방향, 구멍 반시계)대로 읽고, 잘못된 도형(꼬인 고리 등)은 make_valid로 고쳐요.
코드 자릿수(시군구 5, 법정읍면동 8)와 중복을 검사해서 하나라도 어긋나면 파일을 만들지 않아요.
"""

import csv
import glob
import os
import sys
from dataclasses import dataclass

import shapefile
from shapely.geometry import shape
from shapely.validation import make_valid


@dataclass(frozen=True)
class Layer:
    shp: str
    out: str
    code_col: str
    name_col: str
    code_len: int


LAYERS = (
    Layer("TL_SCCO_SIG", "boundary_sig.csv", "SIG_CD", "SIG_KOR_NM", 5),
    Layer("TL_SCCO_EMD", "boundary_emd.csv", "EMD_CD", "EMD_KOR_NM", 8),
)
SIDO_COUNT = 16  # 2026-09 기준 시도 zip 16개 (광주는 전남광주 통합특별시로)

csv.field_size_limit(sys.maxsize)


@dataclass
class Summary:
    rows: int = 0
    points: int = 0
    fixed: int = 0


def convert(src: str, out: str, sido_count: int = SIDO_COUNT) -> dict[str, Summary]:
    os.makedirs(out, exist_ok=True)
    summaries = {}
    for layer in LAYERS:
        files = sorted(glob.glob(os.path.join(src, "[0-9]*", f"{layer.shp}.shp")))
        if len(files) != sido_count:
            raise ValueError(f"{layer.shp}.shp가 시도 폴더 {sido_count}개에 있어야 하는데 {len(files)}개예요")
        rows = list(_read(files, layer))
        summary = Summary(rows=len(rows))
        path = os.path.join(out, layer.out)
        with open(path, "w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(["code", "name", "wkt"])
            for code, name, geom, points, fixed in rows:
                w.writerow([code, name, geom.wkt])
                summary.points += points
                summary.fixed += int(fixed)
        summaries[layer.out] = summary
    return summaries


def _read(files: list[str], layer: Layer):
    seen = set()
    for f in files:
        r = shapefile.Reader(f, encoding="cp949")
        fields = [fl[0] for fl in r.fields[1:]]
        ci, ni = fields.index(layer.code_col), fields.index(layer.name_col)
        for sr in r.iterShapeRecords():
            code = str(sr.record[ci]).strip()
            if len(code) != layer.code_len or not code.isdigit():
                raise ValueError(f"{f}: 코드 '{code}'가 {layer.code_len}자리 숫자가 아니에요")
            if code in seen:
                raise ValueError(f"{f}: 코드 {code}가 두 번 나와요")
            seen.add(code)
            geom = shape(sr.shape.__geo_interface__)
            fixed = not geom.is_valid
            if fixed:
                geom = make_valid(geom)
            yield code, str(sr.record[ni]).strip(), geom, len(sr.shape.points), fixed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        summaries = convert(argv[0], argv[1])
    except ValueError as e:
        print(f"실패: {e}", file=sys.stderr)
        return 1
    for name, s in summaries.items():
        size = os.path.getsize(os.path.join(argv[1], name)) / 1e6
        print(f"{name}: {s.rows}개, 점 {s.points:,}개, 고친 도형 {s.fixed}개, {size:.1f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
