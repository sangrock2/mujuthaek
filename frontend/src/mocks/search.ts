// 화면용 예시 데이터 (디자인 WebSearch · MSearch). 실제 값은 API에서 받아요.

export type SearchType = "공고" | "혜택" | "지역";

/** ok/check는 판정 배지, none은 '지원 불가'(회색), score는 생활권 점수 */
export type SearchBadge =
  { kind: "ok" } | { kind: "check" } | { kind: "none" } | { kind: "score"; score: number };

export type SearchResult = {
  /** 공고는 n*, 혜택은 b*, 지역은 동네 id */
  id: string;
  type: SearchType;
  title: string;
  /** 모바일에서 줄여 쓰는 제목 */
  titleShort?: string;
  meta: string;
  /** 모바일에서 줄여 쓰는 메타 */
  metaShort: string;
  badge: SearchBadge;
  /** 상세 주소 (없으면 종류와 id로 정해요: 사업공간 · 사업 지원은 따로 줘요) */
  href?: string;
};

export type SearchData = {
  query: string;
  /** 결과 제목에서 강조할 검색어 */
  terms: string[];
  recent: string[];
  results: SearchResult[];
};

export const searchData: SearchData = {
  query: "마포 행복주택",
  terms: ["마포", "행복주택"],
  recent: ["청년 월세", "매입임대 서울", "공덕동"],
  results: [
    {
      id: "n1",
      type: "공고",
      title: "○○지구 행복주택 (마포구)",
      meta: "LH · 공공임대 월세형 · 마감 D-12",
      metaShort: "LH · 월세형 · 마감 D-12",
      badge: { kind: "ok" },
    },
    {
      id: "n2",
      type: "공고",
      title: "마포 ○○ 행복주택 예비입주자 모집",
      titleShort: "마포 ○○ 행복주택 예비입주자",
      meta: "SH · 공공임대 월세형 · 마감 D-20",
      metaShort: "SH · 월세형 · 마감 D-20",
      badge: { kind: "check" },
    },
    {
      id: "n3",
      type: "공고",
      title: "상암 ○○ 행복주택 (마포구 상암동)",
      titleShort: "상암 ○○ 행복주택 (마포구)",
      meta: "LH · 신혼부부 대상 · 마감 D-6",
      metaShort: "LH · 신혼부부 대상 · D-6",
      badge: { kind: "none" },
    },
    {
      id: "b1",
      type: "혜택",
      title: "마포구 청년 이사비 지원",
      meta: "마포구 · 최대 40만 원 · 1회",
      metaShort: "마포구 · 최대 40만 원",
      badge: { kind: "ok" },
    },
    {
      id: "b2",
      type: "혜택",
      title: "서울시 청년 월세 지원",
      meta: "서울특별시 · 월 20만 원 · 10월 31일까지",
      metaShort: "서울시 · 월 20만 원",
      badge: { kind: "check" },
    },
    {
      id: "mapo",
      type: "지역",
      title: "마포구 생활권",
      meta: "직장까지 평균 28분 · 역세권 · 숲세권",
      metaShort: "직장까지 평균 28분",
      badge: { kind: "score", score: 82 },
    },
  ],
};
