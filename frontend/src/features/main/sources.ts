// 연동 대상 기관 목록. 현재 수집 가동 상태를 뜻하지 않아요.
export type MainSourceGroup = {
  key: "homes" | "policy" | "business";
  title: string;
  /** PC 칩 이름 */
  items: string[];
  /** 모바일 한 줄 요약 */
  summary: string;
};

export const landingSources: MainSourceGroup[] = [
  {
    key: "homes",
    title: "공공주택 공고",
    items: [
      "LH 청약플러스 · 마이홈",
      "청약홈",
      "SH 서울",
      "청년안심주택",
      "GH 경기",
      "iH 인천",
      "부산",
      "대구",
      "대전",
      "울산",
      "경북",
      "경남",
    ],
    summary: "LH · 청약홈 · SH · 청년안심주택 · GH · iH · 부산 · 대구 · 대전 · 울산 · 경북 · 경남",
  },
  {
    key: "policy",
    title: "주거 · 청년 정책",
    items: ["정부24", "복지로", "온통청년", "지자체 공고"],
    summary: "정부24 · 복지로 · 온통청년 · 지자체 공고",
  },
  {
    key: "business",
    title: "사업공간 · 사업 지원",
    items: ["K-Startup", "기업마당", "공유누리"],
    summary: "K-Startup · 기업마당 · 공유누리",
  },
];
