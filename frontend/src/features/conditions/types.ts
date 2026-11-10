import type { Head, Marry } from "@/features/profile/useProfileForm";

/** 이 기기(localStorage)에 30일 동안 저장하는 조건. 소득·자산은 넣지 않아요 */
export type DeviceConditions = {
  birth: string;
  /** 지금 사는 곳 (지역 코드, 시·군·구 5자리). 거주 요건·순위 판정에만 써요. 모르면 "" */
  regionCode: string;
  /** 찾아볼 지역(이사갈 곳) 코드 (한 곳, 시·도 2자리 또는 시·군·구 5자리). 비어 있으면 전체 */
  searchRegionCodes: string[];
  head: Head;
  statuses: string[];
  marry: Marry;
  kids: number;
  /** 함께 사는 가족 수 (나 포함) "1명" ~ "10명". 모르면 "" */
  householdSize: string;
  homelessPeriod: string;
  bankbookPeriod: string;
  paymentCount: string;
  priorities: string[];
};

/** 저장하지 않는 값. 탭을 닫으면 지워지는 sessionStorage에만 둬요 */
export type SessionConditions = {
  income: string;
  asset: string;
  assetUnknown: boolean;
  /** 자동차 가액 (만 원). 예전에 저장한 값에는 없을 수 있어요 */
  car?: string;
  /** 차가 없어요 (자동차 가액 0원으로 판정) */
  noCar?: boolean;
  available: string;
  rankChecks: string[];
};

export type ConditionsSnapshot =
  | { status: "loading" }
  | {
      status: "ready";
      device: DeviceConditions | null;
      session: SessionConditions | null;
      saveOnDevice: boolean;
      /** 이 기기에 저장한 시각 (ms). 이 기기 저장이 꺼져 있으면 null */
      savedAt: number | null;
    };
