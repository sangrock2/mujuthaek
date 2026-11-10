// 화면용 예시 데이터 (목업 모드). 실제 결과는 API(POST /eligibility/loans/evaluate)에서 받아요.
// 예시 결과는 「만 29세 미혼 · 1인 세대 · 세대원 모두 무주택 · 연소득 5천만 원 이하 · 순자산 기준 이하」로 판정한 모양이고,
// 상품 이름 · 한도 · 금리 · 원문 주소는 백엔드 loan_rules 마이그레이션 값을 옮겼어요. 목업에서는 넣은 값과 상관없이 이 결과를 보여 줘요
import type { LoanForm, LoanItem, LoanResult } from "@/features/loans/loan";

/** 저장한 조건이 없을 때 목업 모드에서 미리 채우는 예시 (금액은 채우지 않아요) */
export const loanExample: LoanForm = {
  birthDate: "1997-03-15",
  marital: "SINGLE",
  children: [],
  householdSize: 1,
  homeless: true,
};

const nhuf = (path: string) => `https://nhuf.molit.go.kr/FP/FP05/${path}`;

const item = (
  i: Omit<LoanItem, "failedConditions" | "checkReasons" | "missingInputs"> &
    Partial<Pick<LoanItem, "failedConditions" | "checkReasons" | "missingInputs">>,
): LoanItem => ({ failedConditions: [], checkReasons: [], missingInputs: [], ...i });

const items: LoanItem[] = [
  item({
    productCode: "BEOTIMMOK_GENERAL",
    productName: "버팀목전세자금",
    loanType: "JEONSE",
    status: "ELIGIBLE",
    limitSummary:
      "수도권 1.2억 원 / 그 외 0.8억 원 (신혼·2자녀 이상 2.5억 원 / 1.6억 원), 보증금의 70% (신혼·2자녀 이상 80%)",
    rateSummary: "연 2.5~3.5%",
    sourceUrl: nhuf("FP0502/FP05020101.jsp"),
  }),
  item({
    productCode: "BEOTIMMOK_YOUTH",
    productName: "청년전용 버팀목전세자금",
    loanType: "JEONSE",
    status: "ELIGIBLE",
    limitSummary: "1.5억 원 (만 25세 미만 단독세대주 1.2억 원), 보증금의 80%",
    rateSummary: "연 2.2~3.3%",
    sourceUrl: nhuf("FP0502/FP05020301.jsp"),
  }),
  item({
    productCode: "YOUTH_MONTHLY_RENT",
    productName: "청년전용 보증부월세대출",
    loanType: "MONTHLY_RENT",
    status: "ELIGIBLE",
    limitSummary: "보증금 4,500만 원 + 월세금 1,200만 원 (24개월, 월 50만 원 이내)",
    rateSummary: "보증금 연 1.3%, 월세금 연 0%(월 20만 원까지)·1.0%(초과분)",
    sourceUrl: nhuf("FP0502/FP05020701.jsp"),
  }),
  item({
    productCode: "HOUSING_STABILITY_MONTHLY_RENT",
    productName: "주거안정월세대출",
    loanType: "MONTHLY_RENT",
    status: "ELIGIBLE",
    limitSummary: "1,440만 원 (월 60만 원 이내)",
    rateSummary:
      "우대형(취업준비생·사회초년생·근로/자녀장려금·주거급여 수급자 등) 연 1.3%, 일반형 연 1.8%",
    sourceUrl: nhuf("FP0502/FP05020201.jsp"),
  }),
  item({
    productCode: "DIDIMDOL_YOUTH_DREAM",
    productName: "청년 주택드림 디딤돌대출",
    loanType: "PURCHASE",
    status: "NEEDS_INPUT",
    checkReasons: [
      "청년 주택드림 통장으로 청약에 당첨되어야 해요 (당첨 때 만 39세 이하, 통장 1년 이상 가입·1천만 원 이상 납입)",
    ],
    limitSummary: "미혼 3억 원, 신혼 4억 원, LTV 70% (생애최초 80%)",
    rateSummary: "연 2.4~4.15%",
    sourceUrl: nhuf("FP0503/FP05030901.jsp"),
  }),
  item({
    productCode: "BEOTIMMOK_NEWLYWED",
    productName: "신혼부부전용 전세자금",
    loanType: "JEONSE",
    status: "INELIGIBLE",
    failedConditions: ["혼인 7년 이내 신혼부부(또는 3개월 안 결혼 예정)여야 해요"],
    limitSummary: "수도권 2.5억 원 / 그 외 1.6억 원, 보증금의 80%",
    rateSummary: "연 1.9~3.3% (신청인 1인 소득으로 받으면 +0.3%p)",
    sourceUrl: nhuf("FP0502/FP05020401.jsp"),
  }),
  item({
    productCode: "BEOTIMMOK_NEWBORN",
    productName: "신생아 특례 버팀목대출",
    loanType: "JEONSE",
    status: "INELIGIBLE",
    failedConditions: ["기준일 전 2년 안에 낳은 자녀가 있어야 해요 (2023년 이후 출생)"],
    limitSummary: "2.4억 원, 보증금의 80%",
    rateSummary: "연 1.3~4.3%",
    sourceUrl: nhuf("FP0502/FP05021401.jsp"),
  }),
  item({
    productCode: "DIDIMDOL",
    productName: "내집마련 디딤돌대출",
    loanType: "PURCHASE",
    status: "INELIGIBLE",
    failedConditions: ["만 30세 미만 미혼 단독세대주는 받을 수 없어요"],
    limitSummary: "2억 원 (생애최초 2.4억 원, 신혼·2자녀 이상 3.2억 원), LTV 70% (생애최초 80%)",
    rateSummary: "연 2.85~4.15%",
    sourceUrl: nhuf("FP0503/FP05030101.jsp"),
  }),
  item({
    productCode: "DIDIMDOL_NEWLYWED",
    productName: "신혼부부전용 구입자금",
    loanType: "PURCHASE",
    status: "INELIGIBLE",
    failedConditions: [
      "만 30세 미만 미혼 단독세대주는 받을 수 없어요",
      "혼인 7년 이내 신혼부부(또는 3개월 안 결혼 예정)여야 해요",
    ],
    limitSummary: "3.2억 원, LTV 80% (수도권·규제지역 70%)",
    rateSummary: "연 2.55~3.85%",
    sourceUrl: nhuf("FP0503/FP05030601.jsp"),
  }),
  item({
    productCode: "DIDIMDOL_NEWBORN",
    productName: "신생아 특례 디딤돌대출",
    loanType: "PURCHASE",
    status: "INELIGIBLE",
    failedConditions: ["기준일 전 2년 안에 낳은 자녀가 있어야 해요 (2023년 이후 출생)"],
    limitSummary: "4억 원, LTV 70% (생애최초 80%)",
    rateSummary: "연 1.8~4.5%",
    sourceUrl: nhuf("FP0503/FP05030801.jsp"),
  }),
];

/** 예시 결과. asOf는 부를 때 오늘로 바꿔요 */
export const loanResultExample = (asOf: string): LoanResult => ({
  asOf,
  counts: { eligible: 4, needsInput: 1, ineligible: 5 },
  items,
});
