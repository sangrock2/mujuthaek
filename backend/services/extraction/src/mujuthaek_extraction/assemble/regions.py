"""원문 지역 표현 → 법정동코드 10자리(모르는 하위 단계는 0).

코드표는 행정표준코드 법정동코드 전체 자료(코드, "서울특별시 종로구 청운동" 형태의 이름, 폐지 여부)를 기준일과 함께 주입합니다.
원문에서 확인한 가장 낮은 단계까지 코드로 만들고, 하나로 정해지지 않으면 상위 단계로 내려가거나 None을 돌려줍니다. 추정하지 않습니다.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# 원문에서 흔한 시도 약칭. 코드표의 공식 이름과 함께 사용합니다.
SIDO_ALIASES = {
    "서울": "서울특별시",
    "서울시": "서울특별시",
    "부산": "부산광역시",
    "부산시": "부산광역시",
    "대구": "대구광역시",
    "대구시": "대구광역시",
    "인천": "인천광역시",
    "인천시": "인천광역시",
    "광주광역시": "광주광역시",
    "대전": "대전광역시",
    "대전시": "대전광역시",
    "울산": "울산광역시",
    "울산시": "울산광역시",
    "세종": "세종특별자치시",
    "세종시": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "강원도": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전라북도": "전북특별자치도",
    "전남": "전라남도",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
    "제주도": "제주특별자치도",
}
# "광주"만 있으면 광주광역시와 경기도 광주시를 구별할 수 없어 약칭으로 쓰지 않습니다.


def _same_sido_names() -> dict[str, frozenset[str]]:
    groups: dict[str, set[str]] = {}
    for alias, full in SIDO_ALIASES.items():
        groups.setdefault(full, {full}).add(alias)
    groups.setdefault("광주광역시", {"광주광역시"})
    return {name: frozenset(same) for same in groups.values() for name in same}


# 시도 이름 → 같은 시도를 가리키는 이름들(정식 이름·약칭: 「충청남도」↔「충남」, 「서울특별시」↔「서울시」↔「서울」).
# 근거 문장의 지역·주소를 비교할 때 씁니다(판정 틀의 지역 확인, 일정 접수 장소 주소 확인)
SIDO_NAMES: dict[str, frozenset[str]] = _same_sido_names()
# 통합으로 폐지된 시도 → 이어받은 시도. 코드표에 옛 이름이 현존하면(이전 기준일 코드표) 쓰지 않습니다.
# 실측: 코드표 2026-09-29 기준 광주광역시·전라남도 폐지 → 전남광주통합특별시. 공고문은 옛 이름을 그대로 써서 시군구 코드가 비었음.
SIDO_SUCCESSORS = {
    "광주광역시": "전남광주통합특별시",
    "전라남도": "전남광주통합특별시",
}
# 한 시도만 담당하는 공급 기관(collector 출처 코드 → 시도). 원문에 "강동구"처럼 시도 없이 적혔을 때만 씁니다.
# LH·마이홈처럼 전국 기관은 넣지 않습니다.
SOURCE_SIDO = {
    "sh": "서울특별시",
    "gh": "경기도",
    "ih": "인천광역시",
    "bmc": "부산광역시",
    "dudc": "대구광역시",
    "dcco": "대전광역시",
    "umca": "울산광역시",
    "gbdc": "경상북도",
    "gndc": "경상남도",
    "jbdc": "전북특별자치도",
}
SIGUNGU_SUFFIX = re.compile(r".+(시|군|구)$")
DONG_SUFFIX = re.compile(r".+(동|읍|면|가|리)$")  # "종로1가"처럼 가로 끝나는 법정동 포함


@dataclass(frozen=True)
class RegionMatch:
    code: str | None
    level: str | None  # SIDO / SIGUNGU / DONG
    note: str | None  # 상위 단계로 내려갔거나 정하지 못한 사유 (검수 메모)


def _clean(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip()


class RegionCodeTable:
    """현존 법정동코드를 이름으로 찾는 코드표입니다. 원문 지역 표현을 확인된 가장 낮은 단계의 코드로 바꿉니다."""

    def __init__(self, rows: Iterable[tuple[str, str, bool]], reference_date: str):
        """rows: (10자리 코드, 공백으로 나눈 전체 이름, 현존 여부). 폐지된 코드는 사용하지 않습니다."""
        self.reference_date = reference_date
        self._by_name: dict[tuple[str, ...], str] = {}
        self._sigungu_by_tail: dict[tuple[str, ...], set[tuple[str, ...]]] = {}
        self._dong_by_name: dict[str, set[tuple[str, ...]]] = {}  # 법정동(읍면동) 이름 → 전체 이름들 (동만 적힌 주소용)
        for code, name, active in rows:
            if not active or not re.fullmatch(r"[0-9]{10}", code):
                continue
            parts = tuple(_clean(name).split())
            self._by_name[parts] = code
            if code[5:] == "00000" and len(parts) >= 2:  # 시군구 단위 (일반구는 "청주시 상당구"처럼 두 단어)
                for size in range(1, len(parts)):
                    self._sigungu_by_tail.setdefault(parts[-size:], set()).add(parts)
            elif code[5:8] != "000" and code[8:] == "00" and len(parts) >= 3:  # 읍면동 단위
                self._dong_by_name.setdefault(parts[-1], set()).add(parts)
        self._sido_names = sorted({p[0] for p in self._by_name} | set(SIDO_ALIASES), key=len, reverse=True)

    @classmethod
    def from_csv(cls, path: Path, reference_date: str) -> RegionCodeTable:
        """공공데이터포털 법정동코드 CSV(법정동코드,법정동명,폐지여부 / 존재·폐지, UTF-8)를 읽습니다."""
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            next(reader)  # 머리글
            return cls(((code, name, status == "존재") for code, name, status in reader), reference_date)

    def lookup(self, region: str | None, default_sido: str | None = None, address: str | None = None) -> RegionMatch:
        """default_sido: 출처가 한 시도뿐인 기관(예: SH → 서울특별시)일 때 원문에 시도가 없으면 사용합니다.
        address: 지역 표현으로 시도까지만(또는 못) 정했을 때 주소로 시군구까지 다시 찾습니다. 서비스는 시군구(앞 5자리)를 쓰므로,
        실측 녹화 165건에서 시도까지만 남은 위치 22개가 모두 주소에 구·동이 있던 특정 단지였습니다(대전 「대전광역시 동구 옥천로…」,
        울산 「달동 1279-1」 등, 2026-10-20). 주소로 찾은 결과가 지역 표현의 시도와 다르면 쓰지 않습니다."""
        first = self._lookup(region, default_sido)
        if not address or not _clean(address):
            return first
        if first.level == "SIGUNGU":
            # 일반구가 있는 시(전주시 52110)를 지역 표현으로 정했는데 주소에 그 시의 구(완산구 52111)가 있으면 구까지 내려갑니다.
            # 서비스는 앞 5자리를 쓰므로 시와 구는 다른 지역입니다. 같은 시의 구일 때만(앞 4자리가 같고 시 코드 5번째 자리가 0)
            found = self._lookup(address, default_sido)
            child = found.level in ("SIGUNGU", "DONG") and found.code[:5] != first.code[:5]
            if child and first.code[4] == "0" and found.code[:4] == first.code[:4]:
                return RegionMatch(found.code, found.level, f"주소({address!r})에 있는 일반구까지 정했습니다.")
            return first
        if first.level is not None and first.level != "SIDO":
            return first
        for text in (address, f"{region} {address}" if region and _clean(region) else None):
            if not text:
                continue
            found = self._lookup(text, default_sido)
            if found.level in ("SIGUNGU", "DONG") and (first.code is None or found.code[:2] == first.code[:2]):
                note = f"지역 표현({region!r})으로는 시군구를 정하지 못해 주소({address!r})로 정했습니다."
                return RegionMatch(found.code, found.level, f"{note} {found.note}" if found.note else note)
        return first

    def _split_glued(self, tokens: list[str], sido: str | None) -> list[str]:
        """띄어쓰기 없이 붙은 주소(「대구북구노원로10길40」)의 앞에서 시도·시군구 이름을 떼어 냅니다. 이름이 하나로 정해질 때만."""
        # 이미 시도·시군구·동 이름인 낱말은 떼지 않습니다(「서울특별시」→「서울」+「특별시」, 「제주시」→「제주」+「시」가 되지 않게)
        known = tokens and (tokens[0] in self._sido_names or (tokens[0],) in self._sigungu_by_tail or tokens[0] in self._dong_by_name)
        if tokens and sido is None and not known:
            for name in self._sido_names:
                if tokens[0].startswith(name) and len(tokens[0]) > len(name):
                    return self._split_glued([name, tokens[0][len(name) :], *tokens[1:]], name)
        return tokens

    def _bare_sigungu(self, token: str, sido: str | None) -> str | None:
        """「전주」「당진」처럼 시·군을 뺀 이름: 「전주시」「당진군」 중 하나로만 정해지면 그 이름. 시도 이름과 겹치는 이름(광주)은 하지 않습니다."""
        if SIGUNGU_SUFFIX.fullmatch(token) or DONG_SUFFIX.fullmatch(token) or any(name.startswith(token) for name in self._sido_names):
            return None
        found = []
        for suffix in ("시", "군"):
            options = self._sigungu_by_tail.get((token + suffix,), set())
            if sido:
                options = {o for o in options if o[0] == sido}
            if options:
                found.append(token + suffix)
        return found[0] if len(found) == 1 else None

    def _glued_sigungu(self, token: str, sido: str) -> list[str] | None:
        """시도 다음에 붙은 「북구노원로10길40」: 그 시도의 시군구 이름 중 앞이 맞는 것이 하나뿐이면 [시군구, 나머지]."""
        names = {o[-1] for tail, options in self._sigungu_by_tail.items() if len(tail) == 1 for o in options if o[0] == sido}
        matched = [n for n in names if token.startswith(n) and len(token) > len(n)]
        return [matched[0], token[len(matched[0]) :]] if len(matched) == 1 else None

    def _lookup(self, region: str | None, default_sido: str | None) -> RegionMatch:
        if not region or not _clean(region):
            return RegionMatch(None, None, "원문 지역 표현이 없습니다.")
        tokens = self._split_glued([t for t in re.split(r"[\s,()]+", _clean(region)) if t], None)
        sido = None
        if tokens:
            alias = SIDO_ALIASES.get(tokens[0])
            name = alias or tokens[0]
            successor = SIDO_SUCCESSORS.get(name)
            if (name,) not in self._by_name and successor and (successor,) in self._by_name:
                name = successor
            if alias or (name,) in self._by_name:
                sido = name
                tokens = tokens[1:]
        explicit = sido is not None  # 원문에 시도가 적혔는지(기관 기본 시도는 짐작일 뿐)
        sido = sido or default_sido
        if tokens and sido and not SIGUNGU_SUFFIX.fullmatch(tokens[0]) and not DONG_SUFFIX.fullmatch(tokens[0]):
            tokens = (self._glued_sigungu(tokens[0], sido) or [tokens[0]]) + tokens[1:]
        if tokens and (bare := self._bare_sigungu(tokens[0], sido)):
            tokens = [bare, *tokens[1:]]

        sigungu_tokens: list[str] = []
        while tokens and SIGUNGU_SUFFIX.fullmatch(tokens[0]) and not DONG_SUFFIX.fullmatch(tokens[0]):
            sigungu_tokens.append(tokens.pop(0))
        dong = tokens[0] if tokens and DONG_SUFFIX.fullmatch(tokens[0]) else None

        if not sigungu_tokens:
            if dong and sido:
                # 동만 적힌 주소(울산 「달동 1279-1」): 그 시도 안에서 그 법정동이 한 시군구에만 있으면 그 동
                places = {p for p in self._dong_by_name.get(dong, set()) if p[0] == sido}
                if len(places) == 1:
                    place = next(iter(places))
                    return RegionMatch(self._by_name[place], "DONG", f"시군구 없이 적힌 '{dong}'을(를) {sido}에서 하나뿐인 법정동으로 찾았습니다.")
            if sido and (sido,) in self._by_name:
                return RegionMatch(self._by_name[(sido,)], "SIDO", None)
            return RegionMatch(None, None, f"시도·시군구를 확인할 수 없습니다: {region!r}")

        everywhere = self._sigungu_by_tail.get(tuple(sigungu_tokens), set())
        options = {o for o in everywhere if o[0] == sido} if sido else everywhere
        if not explicit and sido and not options:
            # 기관 기본 시도 밖의 지역(SH 공고의 "하남시"): 기본 시도로 덮지 않고, 전국에서 하나뿐이면 그것을 씁니다(검토 2026-10-16)
            options = everywhere
            sido = None
        if len(options) != 1:
            reason = "같은 이름의 시군구가 여러 곳입니다" if options else "코드표에 없는 시군구입니다"
            if sido and (sido,) in self._by_name:
                return RegionMatch(self._by_name[(sido,)], "SIDO", f"{reason}: {region!r}. 시도 단위까지만 사용합니다.")
            return RegionMatch(None, None, f"{reason}: {region!r}")

        sigungu = next(iter(options))
        if dong and (*sigungu, dong) in self._by_name:
            return RegionMatch(self._by_name[(*sigungu, dong)], "DONG", None)
        note = f"법정동 '{dong}'을(를) 찾지 못해 시군구 단위까지만 사용합니다(행정동일 수 있음)." if dong else None
        return RegionMatch(self._by_name[sigungu], "SIGUNGU", note)


def from_collector_code(code: str | None) -> str | None:
    """collector raw 이벤트의 시군구 5자리 코드를 10자리로 바꿉니다."""
    return f"{code}00000" if code and re.fullmatch(r"[0-9]{5}", code) else None
