// 화면용 예시 데이터 (디자인 WebMain · MMain 소개 화면의 '예시' 카드). 실제 값은 API에서 받아요.
import type { Verdict } from "@/components/ui/Badge";

export type MainSourceGroup = {
  key: "homes" | "policy" | "business";
  title: string;
  /** PC 칩 이름 */
  items: string[];
  /** 모바일 한 줄 요약 */
  summary: string;
};

export type MainLanding = {
  example: {
    conditions: string[];
    homesCount: string;
    benefitsSummary: string;
    news: { id: string; meta: string; title: string; verdict: Verdict }[];
  };
  judgeExample: {
    title: string;
    meta: string;
    dday: string;
    rows: { label: string; mobileLabel?: string; verdict: Verdict; mobile: boolean }[];
    quoteSource: string;
    quote: string;
    prepareAmount: string;
  };
  sources: MainSourceGroup[];
};

export const mainLanding: MainLanding = {
  example: {
    conditions: ["만 29세", "연소득 3,200만 원", "무주택 4년"],
    homesCount: "7곳",
    benefitsSummary: "연 480만 원 · 5개",
    news: [
      { id: "n1", meta: "새 공고 · LH", title: "○○지구 행복주택 입주자 모집", verdict: "ok" },
      { id: "b1", meta: "새 정책 · ○○시", title: "청년 월세 지원", verdict: "check" },
    ],
  },
  judgeExample: {
    title: "○○지구 행복주택",
    meta: "LH · 공공임대 월세형 · 직장까지 32분",
    dday: "마감 D-12",
    rows: [
      { label: "나이 · 청년 유형", verdict: "ok", mobile: true },
      {
        label: "소득 · 기준중위소득 100% 이하",
        mobileLabel: "소득 · 중위소득 100% 이하",
        verdict: "ok",
        mobile: true,
      },
      { label: "무주택", verdict: "ok", mobile: false },
      {
        label: "자산 · 자동차 가액 포함",
        mobileLabel: "자산 · 자동차 포함",
        verdict: "check",
        mobile: true,
      },
    ],
    quoteSource: "근거 원문 · 공고문 4쪽",
    quote: "“공고일 현재 무주택세대구성원으로서 해당 세대의 월평균 소득이 …”",
    prepareAmount: "1,240만 원",
  },
  sources: [
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
      summary:
        "LH · 청약홈 · SH · 청년안심주택 · GH · iH · 부산 · 대구 · 대전 · 울산 · 경북 · 경남",
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
      items: ["K-Startup", "기업마당", "공유누리", "LH 상가"],
      summary: "K-Startup · 기업마당 · 공유누리 · LH 상가",
    },
  ],
};
