"""큰 자격 기준표 나누기: 기준 행이 많은 원문 자격 기준표를 찾아, 행 대상(공급유형·계층)이 바뀌는 곳에서 묶음으로 나눕니다.
묶음마다 기준표 담당(v2/agents/section.py)이 그 행의 기준만 넣습니다.

2026-11-10 유료 확인 jbdc-16011: 공급유형×공급방식×외벌이·맞벌이 소득표(32행)를 자격 담당 혼자 넣으며 회차마다 32값 중 27개·15개만
넣음(공급방식 행 일부를 빼거나 맞벌이 값을 근거 글에만 적음). 23건 원문에서 기준 행 12개 이상인 표는 5개(jbdc-16011·dcco-24804·
dcco-24812·dudc-8934 둘)였습니다.

찾는 기준은 검증기의 기준표 행 누락 검사(verify/consistency.criteria_tables)와 같습니다: 담당이 맡은 행과 검증기가 빠진 행을 세는 행이
같아야 맡은 행만 알려 줄 수 있습니다. 임대조건·배점·할증 표와 대상 칸이 하나뿐인 단계별 참고 소득표는 거기서 빠집니다.
행은 원문 글자의 줄 번호로 맞춥니다(병합 칸이 많은 표는 같은 줄 글자가 대상마다 되풀이됨).
"""

from __future__ import annotations

from dataclasses import dataclass

from mujuthaek_extraction.v2.document import DocumentModel, Table
from mujuthaek_extraction.verify.consistency import CriteriaRow, criteria_tables

# 담당에게 나눠 맡길 표의 크기: 기준 행 수와 행 대상 수. 기준 행이 이보다 적은 표는 자격 담당이 한 차례에 넣어 왔음(23건 저장 결과)
BIG_TABLE_ROWS = 12
BIG_TABLE_GROUPS = 2
# 묶음 하나의 행 수 상한: 대상마다 조건 하나 + 맞벌이·가구원 수 행은 예외라, 16행이면 항목 8개 안팎(출력 1만 토큰 아래)
CHUNK_ROWS = 16


@dataclass(frozen=True)
class Chunk:
    """기준표 담당 하나가 맡는 행 묶음."""

    table: str  # V2 표 id(t10-1)
    rows: tuple[int, ...]  # 맡은 행 번호(V2 행 id t10-1.r3의 3)
    spots: tuple[int, ...]  # 그 행의 원문 줄 번호(검증기가 빠진 행을 세는 행)
    groups: tuple[str, ...]  # 행 대상 이름(나온 순서)

    @property
    def label(self) -> str:
        """「t10-1 행 r1~r14」(이어진 행) 또는 「t10-1 행 r1·r3·r5」."""
        if list(self.rows) == list(range(self.rows[0], self.rows[-1] + 1)):
            return f"{self.table} 행 r{self.rows[0]}~r{self.rows[-1]}"
        return f"{self.table} 행 " + "·".join(f"r{row}" for row in self.rows)


def criteria_chunks(document: DocumentModel) -> list[Chunk]:
    """원문 자격 기준표 가운데 기준 행이 BIG_TABLE_ROWS 이상이고 행 대상이 BIG_TABLE_GROUPS 이상인 표를 묶음들로. 기준 행이 문서 모델의
    한 표에 다 있지 않으면 그 표는 나누지 않습니다(자격 담당이 지금처럼 넣음)."""
    where = {spot: (table, row) for table in document.tables for row, spot in enumerate(table.spots)}
    chunks: list[Chunk] = []
    for rows in criteria_tables(document.source):
        if len(rows) < BIG_TABLE_ROWS or len({row.group for row in rows if row.group}) < BIG_TABLE_GROUPS:
            continue
        found = [where.get(row.at) for row in rows]
        if None in found or len({table.id for table, _ in found}) != 1:
            continue
        chunks += _split(found[0][0], rows, [position for _, position in found])
    return chunks


def _split(table: Table, rows: list[CriteriaRow], positions: list[int]) -> list[Chunk]:
    """행 대상이 바뀌는 곳에서 끊어 CHUNK_ROWS 이하로 묶습니다. 대상 하나가 CHUNK_ROWS를 넘으면 그 대상을 고르게 나눕니다(_pieces)."""
    runs: list[list[int]] = []  # 같은 대상이 이어진 행들(rows의 순번)
    start = 0
    for end in range(1, len(rows) + 1):
        if end < len(rows) and rows[end].group == rows[start].group:
            continue
        runs += _pieces(list(range(start, end)), rows)
        start = end
    packs: list[list[int]] = []
    for run in runs:
        if packs and len(packs[-1]) + len(run) <= CHUNK_ROWS:
            packs[-1] += run
        else:
            packs.append(list(run))
    return [
        Chunk(
            table.id,
            tuple(positions[i] for i in pack),
            tuple(rows[i].at for i in pack),
            tuple(dict.fromkeys(rows[i].group for i in pack if rows[i].group)),
        )
        for pack in packs
    ]


def _pieces(run: list[int], rows: list[CriteriaRow]) -> list[list[int]]:
    """대상 하나의 행(rows의 순번)을 CHUNK_ROWS 안팎으로 고르게 나눕니다(16행 + 2행 같은 자투리 묶음을 만들지 않게). 위 칸이 병합된 이어진 행
    (맞벌이·가구원 수 행, 앞 빈 칸이 더 많음)은 앞 행과 떼지 않습니다: 한 공급방식의 외벌이·맞벌이 행이 다른 담당에게 가면 기본 조건과 예외가
    따로 넣어짐(코드 검토에서 찾음). 단위 하나가 CHUNK_ROWS를 넘으면 그 단위만 다음 단계(그 안의 앞 빈 칸 수)로 다시 나눕니다: 1행 방식 + 18행 방식이
    [1, 18]로 나뉘어 묶음이 상한을 넘어 출력 한도에 걸릴 수 있었어요(2026-11-10 재검토). 조각은 모두 CHUNK_ROWS 이하입니다."""
    if len(run) <= CHUNK_ROWS:
        return [run]
    lead = min(rows[i].lead for i in run[1:])
    units: list[list[int]] = [[run[0]]]
    for i in run[1:]:
        if rows[i].lead <= lead:
            units.append([])
        units[-1].append(i)
    units = [piece for unit in units for piece in (_pieces(unit, rows) if len(unit) > CHUNK_ROWS else [unit])]
    # 조각 수를 먼저 정하고(올림), 단위 경계 가운데 고른 자리(행 수의 k/조각 수)에 가장 가까운 곳에서 자름. 앞에서부터 목표 크기까지 채우면
    # 18행(2행 단위)이 8 + 8 + 2로 다시 자투리가 생김. 단위 크기가 고르지 않아 상한을 넘는 조각이 생기면 조각 수를 늘림
    ends, total = [], 0
    for unit in units[:-1]:
        total += len(unit)
        ends.append(total)
    for count in range(-(-len(run) // CHUNK_ROWS), len(units) + 1):
        cuts = {min(ends, key=lambda end: abs(end - k * len(run) / count)) for k in range(1, count)} if ends else set()
        pieces: list[list[int]] = [[]]
        for unit in units:
            pieces[-1] += unit
            if sum(map(len, pieces)) in cuts:
                pieces.append([])
        pieces = [piece for piece in pieces if piece]
        if all(len(piece) <= CHUNK_ROWS for piece in pieces):
            return pieces
    return units
