// 시·도와 시·군·구 (코드 기준). 데이터는 GET /api/v1/regions, 받기 전과 목업 모드에선 regionSnapshot
import { regionSnapshot } from "./regions-data";

export type Sigungu = { code: string; name: string };
export type Sido = { code: string; name: string; shortName: string; sigungus: Sigungu[] };
export type RegionTree = { baseDate: string; sidos: Sido[] };

/** 지역 코드: 시·도 2자리("11") 또는 시·군·구 5자리("11440") */
export const isSidoCode = (code: string) => code.length === 2;

// 2026년 개편 전 이름으로 저장한 조건을 읽을 때 써요
const legacySidoNames: Record<string, string> = {
  광주광역시: "12",
  전라남도: "12",
};

/** 지역 트리로 코드 → 이름, 포함 관계를 찾는 도구 */
export function regionIndex(tree: RegionTree) {
  const sidoByCode = new Map(tree.sidos.map((s) => [s.code, s]));
  const sigunguByCode = new Map(
    tree.sidos.flatMap((s) => s.sigungus.map((g) => [g.code, { sido: s, sigungu: g }] as const)),
  );

  const sido = (code: string) => sidoByCode.get(code.slice(0, 2));

  /** "서울 마포구" · 시·도 코드면 "서울". 모르는 코드면 코드 그대로 */
  const label = (code: string) => {
    if (isSidoCode(code)) return sidoByCode.get(code)?.shortName ?? code;
    const hit = sigunguByCode.get(code);
    return hit ? `${hit.sido.shortName} ${hit.sigungu.name}` : code;
  };

  /**
   * 필터 지역(filter)이 공고 지역(code)을 포함하는지.
   * 시·도는 그 시·도 전체, 일반구가 있는 시("용인시")는 그 구("용인시 처인구")까지 포함해요
   */
  const contains = (filter: string, code: string) => {
    if (isSidoCode(filter)) return code.startsWith(filter);
    if (filter === code) return true;
    const city = sigunguByCode.get(filter)?.sigungu.name;
    const target = sigunguByCode.get(code)?.sigungu.name;
    return Boolean(city && target?.startsWith(`${city} `));
  };

  /** 이름으로 저장한 예전 조건 → 코드. 못 찾으면 null */
  const codeByNames = (sidoName: string, sigunguName: string) => {
    const s =
      tree.sidos.find((x) => x.name === sidoName || x.shortName === sidoName) ??
      sidoByCode.get(legacySidoNames[sidoName] ?? "");
    if (!s) return null;
    if (!sigunguName) return s.code;
    return s.sigungus.find((g) => g.name === sigunguName)?.code ?? s.code;
  };

  return { tree, sidos: tree.sidos, sido, label, contains, codeByNames };
}

export type Regions = ReturnType<typeof regionIndex>;

/** API를 받기 전에도 쓸 수 있는 기본 지역 (저장값 변환, 목업) */
export const snapshotRegions = regionIndex(regionSnapshot);
