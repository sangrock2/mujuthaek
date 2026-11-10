// 화면용 예시 데이터 (디자인 WebBenefits · MBenefits · MBenefitDetail). 실제 값은 API에서 받아요.
import type { Verdict } from "@/components/ui/Badge";

export type BenefitCategory = "주거" | "자산형성" | "교통";

/** 내 자격 한 줄: 충족(ok) / 확인 필요(check) / 해당 안 됨(no) */
export type BenefitEligibility = {
  label: string;
  result: "ok" | "check" | "no";
  /** 충족이 아닐 때 이유 (기준만, 내 값은 없어요) */
  reason?: string;
  /** 확인 필요일 때 넣으면 정해지는 입력을 받는 화면. 없으면 원문 확인 (실제 API) */
  inputHref?: string;
};

export type Benefit = {
  id: string;
  cat: BenefitCategory;
  org: string;
  /** 모바일 목록에서 쓰는 짧은 기관명 */
  orgShort: string;
  title: string;
  amount: string;
  /** 모바일 목록에서 쓰는 짧은 지원 내용 */
  amountShort: string;
  dday: string;
  deadline: string;
  verdict: Verdict;
  /** 내 집 '준비할 돈'에 반영되는 혜택 */
  budget: boolean;
  overlap: string;
  elig: BenefitEligibility[];
  how: string[];
  docs: string;
  sourceUrl: string;
  policyUrl: string;
  applyUrl: string;
  /** 판정을 확인 필요로 둔 이유 (정책 내용 확인 중 등) */
  reason?: string;
};

export type BenefitsSummary = {
  asOf: string;
  yearlyAmount: string;
  items: Benefit[];
};

export const benefitCategories: BenefitCategory[] = ["주거", "자산형성", "교통"];

export const benefitsSummary: BenefitsSummary = {
  asOf: "10월 19일",
  yearlyAmount: "약 480만 원",
  items: [
    {
      id: "b1",
      cat: "주거",
      org: "국토교통부 · 복지로",
      orgShort: "국토교통부",
      title: "청년 월세 지원",
      amount: "월 최대 20만 원 · 12개월",
      amountShort: "월 최대 20만 원 · 12개월",
      dday: "D-73",
      deadline: "12월 31일까지",
      verdict: "ok",
      budget: true,
      overlap: "서울시 청년 월세 지원과 함께 받을 수 없어요",
      elig: [
        { label: "나이 · 만 19~34세", result: "ok" },
        { label: "원가구 소득 · 중위소득 100% 이하", result: "ok" },
        { label: "본인 소득 · 중위소득 60% 이하", result: "ok" },
        { label: "보증금 5천만 원 · 월세 70만 원 이하", result: "check" },
      ],
      how: [
        "복지로 또는 주민센터에서 신청",
        "임대차계약서와 월세 이체 내역 제출",
        "심사 후 매달 지급",
      ],
      docs: "임대차계약서, 월세 이체 내역, 통장 사본",
      sourceUrl: "#",
      policyUrl: "#",
      applyUrl: "#",
    },
    {
      id: "b2",
      cat: "주거",
      org: "주택도시기금",
      orgShort: "주택도시기금",
      title: "청년 전용 버팀목 전세자금 대출",
      amount: "최대 2억 원 · 연 2%대 금리",
      amountShort: "최대 2억 원 · 연 2%대",
      dday: "상시",
      deadline: "상시",
      verdict: "ok",
      budget: true,
      overlap: "다른 전세자금 대출과 함께 받을 수 없어요",
      elig: [
        { label: "나이 · 만 19~34세", result: "ok" },
        { label: "연소득 5천만 원 이하", result: "ok" },
        { label: "무주택 세대주", result: "ok" },
        { label: "순자산 기준", result: "check" },
      ],
      how: [
        "기금e든든에서 대출 가능 여부 확인",
        "취급 은행에 방문 신청",
        "심사 후 집주인에게 바로 지급",
      ],
      docs: "임대차계약서, 소득 증빙, 주민등록등본",
      sourceUrl: "#",
      policyUrl: "#",
      applyUrl: "#",
    },
    {
      id: "b3",
      cat: "주거",
      org: "서울특별시",
      orgShort: "서울특별시",
      title: "서울시 청년 월세 지원",
      amount: "월 20만 원 · 최대 10개월",
      amountShort: "월 20만 원 · 최대 10개월",
      dday: "D-12",
      deadline: "10월 31일까지",
      verdict: "check",
      budget: true,
      overlap: "국토교통부 청년 월세 지원과 함께 받을 수 없어요",
      elig: [
        { label: "서울 거주", result: "ok" },
        { label: "나이 · 만 19~39세", result: "ok" },
        { label: "기준중위소득 150% 이하", result: "ok" },
        { label: "월세 계약 기간", result: "check" },
      ],
      how: ["서울주거포털에서 신청", "선정 결과 문자 안내", "두 달마다 지급"],
      docs: "임대차계약서, 월세 이체 내역",
      sourceUrl: "#",
      policyUrl: "#",
      applyUrl: "#",
    },
    {
      id: "b4",
      cat: "자산형성",
      org: "금융위원회 · 서민금융진흥원",
      orgShort: "서민금융진흥원",
      title: "청년도약계좌",
      amount: "정부 기여금 월 최대 3만 3천 원",
      amountShort: "정부 기여금 월 최대 3만 3천 원",
      dday: "매달 신청",
      deadline: "매달 정해진 기간",
      verdict: "ok",
      budget: false,
      overlap: "청년희망적금과 함께 가입할 수 없어요",
      elig: [
        { label: "나이 · 만 19~34세", result: "ok" },
        { label: "개인 소득 7,500만 원 이하", result: "ok" },
        { label: "가구 소득 · 중위소득 250% 이하", result: "ok" },
      ],
      how: ["은행 앱에서 가입 신청", "소득·가구 심사", "계좌 개설 후 매달 납입"],
      docs: "없음 (앱에서 확인해요)",
      sourceUrl: "#",
      policyUrl: "#",
      applyUrl: "#",
    },
    {
      id: "b5",
      cat: "교통",
      org: "국토교통부",
      orgShort: "국토교통부",
      title: "K-패스",
      amount: "대중교통비 30% 환급 (청년)",
      amountShort: "대중교통비 30% 환급 (청년)",
      dday: "상시",
      deadline: "상시",
      verdict: "ok",
      budget: false,
      overlap: "알뜰교통카드와 함께 쓸 수 없어요",
      elig: [
        { label: "나이 · 만 19~34세", result: "ok" },
        { label: "월 15회 이상 대중교통 이용", result: "check" },
      ],
      how: ["K-패스 카드 발급", "K-패스 누리집 회원가입", "다음 달 자동 환급"],
      docs: "없음",
      sourceUrl: "#",
      policyUrl: "#",
      applyUrl: "#",
    },
  ],
};
