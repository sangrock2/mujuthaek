"use client";

import { useMemo, useState } from "react";
import { birthDateOf } from "@/features/conditions/applicant";
import { useConditions } from "@/features/conditions/store";
import type { DeviceConditions } from "@/features/conditions/types";
import { USE_MOCKS } from "@/lib/api/config";
import { useScore, useScoreProfile } from "./queries";
import type { ScoreInput, ScoreItemKey } from "./score";

/** 화면 입력: 가점 입력 + 「집을 가진 적이 없어요」(무주택 시작 = 태어난 달) */
export type ScoreForm = ScoreInput & { neverOwned?: boolean };

const maritalOf = { single: "SINGLE", married: "MARRIED", planned: "ENGAGED" } as const;

/**
 * 저장한 조건으로 미리 채우기. 조건은 기간을 구간으로만 저장해서 무주택 시작 · 혼인신고 · 통장 가입 연월은 비워 둬요.
 * 부양가족은 배우자 + 자녀로만 채워요 (부모님은 3년 이상 같은 등본이어야 해서 직접 더해요)
 */
function prefillOf(device: DeviceConditions): ScoreForm {
  const owner = device.homelessPeriod === "집이 있어요";
  return {
    birthDate: birthDateOf(device.birth),
    marital: maritalOf[device.marry],
    homeOwner: owner ? true : device.homelessPeriod ? false : undefined,
    dependents: (device.marry === "married" ? 1 : 0) + device.kids,
  };
}

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const DAY = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

/**
 * 서버에 보낼 수 있는 값만 남겨요: 형식이 틀리거나 앞날인 값은 빈 칸으로 (그 항목은 「넣으면 계산돼요」).
 * 혼인신고는 기혼일 때만, 무주택 시작은 집이 없을 때만 써요
 */
export function cleanInput(f: ScoreForm, today: string): ScoreInput {
  const month = (m?: string) => (m && MONTH.test(m) && m <= today.slice(0, 7) ? m : undefined);
  const birthDate =
    f.birthDate && DAY.test(f.birthDate) && f.birthDate < today ? f.birthDate : undefined;
  const dependents =
    f.dependents !== undefined && Number.isInteger(f.dependents) && f.dependents >= 0
      ? Math.min(f.dependents, 20)
      : undefined;
  return {
    birthDate,
    marital: f.marital,
    marriedOn: f.marital === "MARRIED" ? month(f.marriedOn) : undefined,
    homeOwner: f.homeOwner,
    homelessSince: f.homeOwner
      ? undefined
      : f.neverOwned
        ? birthDate?.slice(0, 7)
        : month(f.homelessSince),
    dependents,
    joinedOn: month(f.joinedOn),
  };
}

/** "2026-11-11" (한국 날짜) */
const seoulToday = () =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());

/**
 * 가점 계산기 상태: 저장한 조건으로 미리 채우고, 바꾸면 다시 계산해요. 점수는 백엔드 기준이에요(목업은 같은 규칙을 화면에서).
 * 입력은 이 화면 메모리에만 있어요 (저장하지 않아요)
 */
export function useScoreCalculator() {
  const { data: profile } = useScoreProfile();
  const stored = useConditions();
  const [edited, setEdited] = useState<ScoreForm | null>(null);
  // 저장값을 읽은 뒤(브라우저)에만 채우고 오늘 날짜를 써요 (빌드 때 미리 그리는 화면에는 날짜를 넣지 않아요)
  const ready = stored.status === "ready";
  const device = ready ? stored.device : null;
  const prefill = useMemo<ScoreForm | null>(() => {
    if (!ready) return null;
    if (device) return prefillOf(device);
    return USE_MOCKS ? profile.example : {};
  }, [ready, device, profile.example]);
  const form = edited ?? prefill;
  const today = useMemo(() => (ready ? seoulToday() : null), [ready]);
  const input = useMemo(() => (form && today ? cleanInput(form, today) : null), [form, today]);
  const { score, updating, error } = useScore(input, today);

  const total = score?.total ?? 0;
  const pointsOf = (key: ScoreItemKey) => score?.items.find((i) => i.key === key) ?? null;

  return {
    profile,
    form: form ?? {},
    today,
    score,
    pointsOf,
    total,
    /** 빈 칸이 있어 아는 항목만 더한 점수 */
    partial: Boolean(score?.missingInputs.length),
    diff: total - profile.cutoff.score,
    updating,
    error,
    set: (patch: Partial<ScoreForm>) => setEdited({ ...(form ?? {}), ...patch }),
  };
}

export type ScoreCalculator = ReturnType<typeof useScoreCalculator>;
