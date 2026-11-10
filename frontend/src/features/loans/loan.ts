// 대출 자격 확인 (주택도시기금 전세·월세·구입 대출). 기준은 백엔드 POST /api/v1/eligibility/loans/evaluate예요.
// 정확한 소득·순자산·생년월일을 다루니 이 화면 메모리에만 두고, 저장(localStorage·서버)·로그·분석 이벤트에 넣지 않아요

export type LoanMarital = "SINGLE" | "ENGAGED" | "MARRIED" | "DIVORCED" | "WIDOWED";

/** 화면 입력. 금액은 만 원 단위 글자("3,800")로 받아요 */
export type LoanForm = {
  /** 생년월일 "1997-03-15" */
  birthDate?: string;
  marital?: LoanMarital;
  /** 혼인신고일 "2024-05-18" (기혼일 때만) */
  marriedOn?: string;
  /** 자녀 생년월일. undefined = 아직 답하지 않음, [] = 자녀 없음, "" = 아직 비운 칸 */
  children?: string[];
  /** 세대 가구원 수 (나 포함) */
  householdSize?: number;
  /** 세대원 모두 집이 없으면 true */
  homeless?: boolean;
  /** 부부 모두 소득이 있으면 true (기혼·결혼 예정일 때만) */
  dualIncome?: boolean;
  /** 부부합산 연소득 (미혼이면 본인), 만 원 */
  incomeMan?: string;
  /** 본인 연소득, 만 원 (기혼·결혼 예정일 때만) */
  myIncomeMan?: string;
  /** 부부합산 자산 합계, 만 원 */
  assetMan?: string;
  /** 부부합산 부채 합계, 만 원. 비우면 0원으로 셈 */
  debtMan?: string;
  /** 세대원 모두 집을 산 적이 없으면 true (구입 대출) */
  firstHome?: boolean;
};

/** POST 본문 profile (백엔드 JudgmentApplicantRequest 중 대출에 쓰는 칸). 빈 칸은 보내지 않아요 */
export type LoanProfile = {
  birthDate?: string;
  maritalStatus?: LoanMarital;
  marriedOn?: string;
  childBirthDates?: string[];
  household?: { size?: number; homeless?: boolean; dualIncome?: boolean };
  loan?: {
    annualIncomeWon?: number;
    applicantAnnualIncomeWon?: number;
    netAssetWon?: number;
    firstHomePurchase?: boolean;
  };
};

export type LoanType = "JEONSE" | "MONTHLY_RENT" | "PURCHASE";
export type LoanStatus = "ELIGIBLE" | "NEEDS_INPUT" | "INELIGIBLE";

/** 백엔드 LoanResult.Item */
export type LoanItem = {
  productCode: string;
  productName: string;
  loanType: LoanType;
  status: LoanStatus;
  /** 받을 수 없는 이유 (넣은 값은 들어 있지 않아요) */
  failedConditions: string[];
  /** 확인이 필요한 이유 */
  checkReasons: string[];
  /** 넣으면 결과가 정해질 수 있는 입력 */
  missingInputs: { field: string; label: string }[];
  limitSummary: string;
  rateSummary: string;
  sourceUrl: string;
};

/** 백엔드 LoanResult */
export type LoanResult = {
  asOf: string;
  counts: { eligible: number; needsInput: number; ineligible: number };
  items: LoanItem[];
};

export const loanTypeLabel: Record<LoanType, string> = {
  JEONSE: "전세",
  MONTHLY_RENT: "월세",
  PURCHASE: "구입",
};

export const loanStatusLabel: Record<LoanStatus, string> = {
  ELIGIBLE: "받을 수 있어요",
  NEEDS_INPUT: "확인 필요",
  INELIGIBLE: "받을 수 없어요",
};

/** 만 원 칸 최대 자릿수 (9,999억 9,999만 원까지, 서버 상한 1,000조 원보다 작아요) */
export const MAN_MAX_DIGITS = 8;

/** "3,800" → 38000000 (원). 비었으면 undefined */
export function manToWon(v: string | undefined) {
  const digits = (v ?? "").replace(/\D/g, "").slice(0, MAN_MAX_DIGITS);
  return digits ? Number(digits) * 10_000 : undefined;
}

/** 입력 중인 만 원 칸을 "3,800"처럼 */
export function formatMan(v: string) {
  const digits = v
    .replace(/\D/g, "")
    .replace(/^0+(?=\d)/, "")
    .slice(0, MAN_MAX_DIGITS);
  return digits ? Number(digits).toLocaleString("ko-KR") : "";
}

/** 원 → "3억 4,500만 원" (음수는 앞에 −) */
export function wonText(won: number) {
  const sign = won < 0 ? "−" : "";
  const abs = Math.abs(won);
  const eok = Math.floor(abs / 100_000_000);
  const man = Math.floor((abs % 100_000_000) / 10_000);
  const parts = [];
  if (eok) parts.push(`${eok.toLocaleString("ko-KR")}억`);
  if (man || !eok) parts.push(`${man.toLocaleString("ko-KR")}만`);
  return `${sign}${parts.join(" ")} 원`;
}

/** 혼인했거나 결혼 예정이면 부부 소득을 나눠 물어요 */
export const isCouple = (m?: LoanMarital) => m === "MARRIED" || m === "ENGAGED";

const DAY = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

/** 순자산 = 자산 − 부채. 자산을 비우면 모름 (부채만으로는 계산하지 않아요) */
export function netAssetWon(f: LoanForm) {
  const asset = manToWon(f.assetMan);
  if (asset === undefined) return undefined;
  return asset - (manToWon(f.debtMan) ?? 0);
}

/** 화면 입력의 문제 (서버가 400으로 막을 값). 있으면 「확인하기」를 막고 칸 아래에 보여 줘요 */
export function formProblems(f: LoanForm) {
  const income = manToWon(f.incomeMan);
  const mine = manToWon(f.myIncomeMan);
  return {
    myIncome:
      isCouple(f.marital) && income !== undefined && mine !== undefined && mine > income
        ? "본인 연소득은 부부합산 연소득보다 클 수 없어요"
        : null,
  };
}

/**
 * 화면 입력 → POST 본문 profile. 형식이 틀리거나 앞날인 날짜는 빈 칸으로 보내요(그 조건은 확인 필요).
 * 자녀 생년월일은 모두 넣었을 때만 보내요: 일부만 보내면 자녀 수를 적게 세어 「받을 수 없음」이 틀릴 수 있어서예요
 */
export function toLoanProfile(f: LoanForm, today: string): LoanProfile {
  const day = (d?: string) => (d && DAY.test(d) && d <= today ? d : undefined);
  const couple = isCouple(f.marital);
  const children =
    f.children && f.children.every((c) => day(c) !== undefined) ? f.children : undefined;
  return {
    birthDate: day(f.birthDate),
    maritalStatus: f.marital,
    marriedOn: f.marital === "MARRIED" ? day(f.marriedOn) : undefined,
    childBirthDates: children,
    household: {
      size: f.householdSize,
      homeless: f.homeless,
      dualIncome: couple ? f.dualIncome : f.marital ? false : undefined,
    },
    loan: {
      annualIncomeWon: manToWon(f.incomeMan),
      applicantAnnualIncomeWon: couple ? manToWon(f.myIncomeMan) : manToWon(f.incomeMan),
      netAssetWon: netAssetWon(f),
      firstHomePurchase: f.firstHome,
    },
  };
}

/** "2026-11-11" (한국 날짜) */
export const seoulToday = () =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
