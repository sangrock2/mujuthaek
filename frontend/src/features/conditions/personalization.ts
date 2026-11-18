"use client";

import { toApplicant } from "./applicant";
import { useConditions } from "./store";
import { useCriteria } from "@/features/eligibility/criteria";

/** 저장 버튼을 눌렀어도 빈 조건이면 개인별 자격을 확인한 것으로 안내하지 않아요. */
export function useHasHousingInput() {
  const stored = useConditions();
  const criteria = useCriteria();
  return (
    stored.status === "ready" &&
    Object.values(toApplicant(stored.device, stored.session, criteria.data)).some(
      (value) => value !== undefined,
    )
  );
}
