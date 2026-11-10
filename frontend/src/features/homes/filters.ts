// 내 집 목록 필터 · 정렬 (지역 · 입주 방식 · 유형 · 정렬 · 지원 불가 보기는 맞춤 목록 API로 보내요)

export const moveInModes = ["빌려서 들어가기", "사서 들어가기"] as const;
export type MoveInMode = (typeof moveInModes)[number];

export const sortOptions = ["추천순", "마감 임박순", "준비할 돈 적은순", "생활권 점수순"] as const;
export type SortOption = (typeof sortOptions)[number];

/** 정렬 → 맞춤 목록 API의 sort. 추천순 = 지원 가능 → 확인 필요 → 마감 임박 → 생활권 */
export const sortParam = {
  추천순: "RECOMMENDED",
  "마감 임박순": "DEADLINE",
  "준비할 돈 적은순": "PREPARE_COST",
  "생활권 점수순": "AREA_SCORE",
} as const satisfies Record<SortOption, string>;

export const tenureParam = {
  "빌려서 들어가기": "RENT",
  "사서 들어가기": "BUY",
} as const;

export const filterGroups = [
  {
    key: "type",
    legend: "유형",
    options: [
      { key: "rentMonthly", label: "공공임대 월세형" },
      { key: "rentJeonse", label: "공공임대 전세형" },
      { key: "private", label: "민간임대" },
    ],
  },
  {
    key: "verdict",
    legend: "내 판정",
    options: [
      { key: "ok", label: "지원 가능" },
      { key: "check", label: "확인 필요" },
      { key: "ineligible", label: "지원 불가도 보기" },
    ],
  },
] as const;
// 공급 기관(LH · 지방 공사 · 청약홈)은 뺐어요: 백엔드가 기관 이름 그대로(LH · SH · 울산도시공사 …) 맞춰 보기만 해서
// 「지방 공사」처럼 묶어 거를 수 없고, 화면에서만 켜고 꺼지는 칸이었어요

export type FilterKey = (typeof filterGroups)[number]["options"][number]["key"];
type TypeKey = (typeof filterGroups)[0]["options"][number]["key"];

/** 유형 → 맞춤 목록 API의 noticeTypes (백엔드 NoticeType). 빌려서 들어가기에서만 써요 */
const typeCodes: Record<TypeKey, string[]> = {
  rentMonthly: [
    "PUBLIC_RENTAL",
    "INTEGRATED_PUBLIC_RENTAL",
    "HAPPY_HOUSING",
    "NATIONAL_RENTAL",
    "PERMANENT_RENTAL",
    "PURCHASE_RENTAL",
  ],
  rentJeonse: ["JEONSE_RENTAL", "LONG_TERM_JEONSE"],
  private: ["PUBLIC_SUPPORT_PRIVATE_RENTAL", "YOUTH_SAFE_HOUSING"],
};

/** 고른 유형의 공고 유형 코드. 다 켜거나 다 끄면 거르지 않아요(undefined) */
export function noticeTypesOf(checked: Record<FilterKey, boolean>): string[] | undefined {
  const keys = Object.keys(typeCodes) as TypeKey[];
  const on = keys.filter((k) => checked[k]);
  if (on.length === 0 || on.length === keys.length) return undefined;
  return on.flatMap((k) => typeCodes[k]);
}

export const defaultChecked: Record<FilterKey, boolean> = {
  rentMonthly: true,
  rentJeonse: true,
  private: true,
  ok: true,
  check: true,
  ineligible: false,
};

export const defaultMode: MoveInMode = "빌려서 들어가기";
export const defaultSort: SortOption = "추천순";

/** 기본값에서 바꾼 필터 수 (모바일 「필터 N」) */
export function changedFilterCount(
  checked: Record<FilterKey, boolean>,
  mode: MoveInMode,
  sort: SortOption,
): number {
  const keys = Object.keys(defaultChecked) as FilterKey[];
  return (
    keys.filter((k) => checked[k] !== defaultChecked[k]).length +
    (mode !== defaultMode ? 1 : 0) +
    (sort !== defaultSort ? 1 : 0)
  );
}
