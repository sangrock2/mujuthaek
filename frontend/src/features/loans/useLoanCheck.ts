"use client";

import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { birthDateOf } from "@/features/conditions/applicant";
import { useConditions } from "@/features/conditions/store";
import type { DeviceConditions } from "@/features/conditions/types";
import { api, ApiError } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import { loanExample, loanResultExample } from "@/mocks/loans";
import {
  formProblems,
  seoulToday,
  toLoanProfile,
  type LoanForm,
  type LoanProfile,
  type LoanResult,
} from "./loan";

const maritalOf = { single: "SINGLE", married: "MARRIED", planned: "ENGAGED" } as const;

/** 함께 사는 가족 수 "3명" → 3 */
const sizeOf = (v: string) => (/^\d+명$/.test(v) ? Number.parseInt(v, 10) : undefined);

const EMPTY: LoanForm = {};

/** 자녀 칸을 이만큼까지 열어요 */
export const CHILD_MAX = 6;

/**
 * 저장한 조건으로 미리 채우기. 저장한 조건에는 정확한 금액 · 날짜가 없어서 생년월일 · 혼인 · 자녀 수 · 가구원 수만 채워요.
 * 자녀는 수만큼 빈 생년월일 칸을 열고, 「세대원 모두 무주택」은 집이 있다고 했을 때만 「아니요」로 채워요
 * (집이 없다고 해도 다른 세대원 집은 모르니 직접 고르게 해요)
 */
function prefillOf(device: DeviceConditions): LoanForm {
  const kids = Math.min(Math.max(device.kids, 0), CHILD_MAX);
  return {
    birthDate: birthDateOf(device.birth),
    marital: maritalOf[device.marry],
    children: Array.from({ length: kids }, () => ""),
    householdSize: sizeOf(device.householdSize),
    homeless: device.homelessPeriod === "집이 있어요" ? false : undefined,
  };
}

/** 목업: 잠깐 기다린 뒤 예시 결과 */
const mockEvaluate = (asOf: string) =>
  new Promise<LoanResult>((resolve) => setTimeout(() => resolve(loanResultExample(asOf)), 300));

/**
 * 대출 자격 확인 상태. 입력은 이 화면 메모리에만 있고(저장하지 않아요), 「확인하기」를 누를 때만 서버에 물어요.
 * 서버도 저장 · 캐시하지 않아요(no-store). 분석 이벤트는 보내지 않아요
 */
export function useLoanCheck() {
  const stored = useConditions();
  const [edited, setEdited] = useState<LoanForm | null>(null);
  /** 마지막으로 확인한 입력 (바뀌었는지 보려고 메모리에만 둬요) */
  const [checkedKey, setCheckedKey] = useState<string | null>(null);
  const ready = stored.status === "ready";
  const device = ready ? stored.device : null;
  const prefill = useMemo<LoanForm | null>(() => {
    if (!ready) return null;
    if (device) return prefillOf(device);
    return USE_MOCKS ? loanExample : {};
  }, [ready, device]);
  const form = edited ?? prefill ?? EMPTY;
  // 저장값을 읽은 뒤(브라우저)에만 오늘 날짜를 써요 (빌드 때 미리 그리는 화면에는 날짜를 넣지 않아요)
  const today = useMemo(() => (ready ? seoulToday() : null), [ready]);
  const profile = useMemo(() => (today ? toLoanProfile(form, today) : null), [form, today]);
  const key = profile ? JSON.stringify(profile) : null;
  const problems = formProblems(form);

  const evaluate = useMutation({
    mutationFn: (p: LoanProfile) =>
      USE_MOCKS
        ? mockEvaluate(today ?? seoulToday())
        : api.post<LoanResult>(endpoints.loanEvaluate, { profile: p }),
    // 입력이 담긴 요청을 화면을 떠나면 바로 잊어요
    gcTime: 0,
    retry: false,
  });

  const error = evaluate.error
    ? evaluate.error instanceof ApiError && evaluate.error.status === 400
      ? "입력 형식이 맞지 않아요. 금액과 날짜를 다시 확인해 주세요"
      : "결과를 받지 못했어요. 잠시 뒤 다시 확인해 주세요"
    : null;

  return {
    form,
    today,
    ready,
    problems,
    result: evaluate.data ?? null,
    pending: evaluate.isPending,
    error,
    /** 결과를 받은 뒤 입력을 바꿨어요 (결과는 앞 입력 기준) */
    stale: Boolean(evaluate.data) && checkedKey !== key,
    canCheck: Boolean(profile) && !problems.myIncome && !evaluate.isPending,
    set: (patch: Partial<LoanForm>) => setEdited({ ...form, ...patch }),
    check: () => {
      if (!profile || problems.myIncome) return;
      setCheckedKey(key);
      evaluate.mutate(profile);
    },
    /** 넣은 값과 결과를 모두 지워요 */
    clear: () => {
      setEdited({});
      setCheckedKey(null);
      evaluate.reset();
    },
  };
}

export type LoanCheck = ReturnType<typeof useLoanCheck>;
