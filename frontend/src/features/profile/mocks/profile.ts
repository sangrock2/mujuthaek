// 화면용 예시 데이터 (디자인 WebProfile · MProfile). 실제 값은 API에서 받아요.

export type ProfilePreview = { homes: number; benefits: number; needCheck: number };

export type ProfileOptions = {
  homelessPeriod: string[];
  bankbookPeriod: string[];
  priorities: string[];
};

/** 공공임대 순위를 보는 세부 요건. any = 하나라도, all = 모두 해당하면 그 순위 */
export type RankCriteria = {
  rank: 1 | 2 | 3;
  rule: "any" | "all";
  items: { key: string; label: string }[];
};

export type ProfileFormData = {
  options: ProfileOptions;
  /** 단계별 '지금 조건으로' 미리보기 (1·2·3단계) */
  previewByStep: [ProfilePreview, ProfilePreview, ProfilePreview];
  /** 처음 골라 둔 우선순위 */
  defaultPriorities: string[];
  /** 지금 상황 (선택, 여러 개) */
  statuses: string[];
  /** 순위 확인용 세부 요건 (선택). 기준 금액은 공고마다 달라질 수 있어요 */
  rankCriteria: RankCriteria[];
};

export const profileFormData: ProfileFormData = {
  options: {
    homelessPeriod: [
      "3년 이상 5년 미만",
      "1년 미만",
      "1년 이상 3년 미만",
      "5년 이상",
      "집이 있어요",
    ],
    bankbookPeriod: ["2년 이상", "1~2년", "6개월~1년", "6개월 미만", "없어요"],
    priorities: ["직장", "대중교통", "학군", "공원", "편의시설", "병원"],
  },
  previewByStep: [
    { homes: 3, benefits: 2, needCheck: 4 },
    { homes: 5, benefits: 4, needCheck: 3 },
    { homes: 7, benefits: 5, needCheck: 2 },
  ],
  defaultPriorities: ["직장", "대중교통"],
  statuses: ["대학생", "취업준비생", "청년", "신혼부부"],
  rankCriteria: [
    {
      rank: 1,
      rule: "any",
      items: [
        { key: "r1-basic", label: "수급자 가구" },
        { key: "r1-near", label: "차상위계층 가구" },
        { key: "r1-single", label: "지원대상 한부모 가족" },
      ],
    },
    {
      rank: 2,
      rule: "all",
      items: [
        { key: "r2-income", label: "본인과 부모의 월평균소득 100% 이하 가구" },
        { key: "r2-asset", label: "총자산가액 34,500만 원 이하" },
      ],
    },
    {
      rank: 3,
      rule: "all",
      items: [
        { key: "r3-income", label: "본인의 월평균소득 100% 이하 가구" },
        { key: "r3-asset", label: "총자산가액 25,100만 원 이하" },
        { key: "r3-car", label: "자동차가액 4,542만 원 이하" },
      ],
    },
  ],
};
