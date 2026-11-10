"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import {
  clearConditions,
  saveConditions,
  setSaveOnDevice,
  useConditions,
} from "@/features/conditions/store";
import type { DeviceConditions, SessionConditions } from "@/features/conditions/types";
import { birthProblem } from "@/components/profile/BirthField";
import { routes, safeNext } from "@/lib/routes";
import type { ProfileFormData, RankCriteria } from "@/mocks/profile";
import { useConditionsPreview } from "./preview";
import { useProfileFormData } from "./queries";

export type Head = "head" | "member";
export type Marry = "single" | "married" | "planned";

export const headOptions: { key: Head; label: string }[] = [
  { key: "head", label: "세대주예요" },
  { key: "member", label: "세대원이에요" },
];

export const marryOptions: { key: Marry; label: string }[] = [
  { key: "single", label: "미혼" },
  { key: "married", label: "기혼" },
  { key: "planned", label: "결혼 예정" },
];

/** 체크한 세부 요건으로 가장 높은 순위를 찾아요. 없으면 null */
export function estimateRank(criteria: RankCriteria[], checked: string[]) {
  const sorted = [...criteria].sort((a, b) => a.rank - b.rank);
  const hit = sorted.find((c) =>
    c.rule === "any"
      ? c.items.some((i) => checked.includes(i.key))
      : c.items.every((i) => checked.includes(i.key)),
  );
  return hit?.rank ?? null;
}

/** 가구원 수 − / + 범위 (나 포함) */
export const MIN_HOUSEHOLD = 1;
export const MAX_HOUSEHOLD = 10;

/** "3명" → 3. 모르면(빈 값) null */
const householdCount = (v: string) => (/^\d+명$/.test(v) ? Number.parseInt(v, 10) : null);

const toggle = (xs: string[], x: string) =>
  xs.includes(x) ? xs.filter((v) => v !== x) : [...xs, x];

function defaultDevice(data: ProfileFormData): DeviceConditions {
  const { options } = data;
  return {
    birth: "",
    regionCode: "",
    searchRegionCodes: [],
    head: "head",
    statuses: [],
    marry: "single",
    kids: 0,
    householdSize: `${MIN_HOUSEHOLD}명`,
    homelessPeriod: options.homelessPeriod[0],
    bankbookPeriod: options.bankbookPeriod[0],
    paymentCount: "",
    priorities: data.defaultPriorities,
  };
}

const emptySession: SessionConditions = {
  income: "",
  asset: "",
  assetUnknown: false,
  car: "",
  noCar: false,
  available: "",
  rankChecks: [],
};

type TextKey = "birth" | "homelessPeriod" | "bankbookPeriod" | "paymentCount";
type SessionTextKey = "income" | "asset" | "car" | "available";

/** 조건 입력 3단계 상태 (PC/모바일 공통). 처음 값은 이 기기에 저장한 조건에서 가져와요 */
export function useProfileForm() {
  const { data } = useProfileFormData();
  const router = useRouter();
  /** 확인하기 뒤 갈 곳 (?next=/homes). 없으면 홈 */
  const next = safeNext(useSearchParams().get("next")) ?? routes.home;
  const stored = useConditions();
  const [step, setStep] = useState(1);
  const [device, setDevice] = useState<DeviceConditions>(() => defaultDevice(data));
  const [sess, setSess] = useState<SessionConditions>(emptySession);
  const [loaded, setLoaded] = useState(false);
  /** 생년월일이 맞지 않아 1단계에서 막혔는지 (그때부터 이유를 보여 줘요) */
  const [birthBlocked, setBirthBlocked] = useState(false);

  // 저장소를 읽을 수 있게 되면 한 번만 이어서 채워요 (렌더 중 상태 맞추기)
  if (!loaded && stored.status === "ready") {
    setLoaded(true);
    if (stored.device) setDevice({ ...defaultDevice(data), ...stored.device });
    if (stored.session) setSess({ ...emptySession, ...stored.session });
  }

  // 「지금 조건으로」: 입력 중인 조건으로 바로 세요 (목업은 단계별 예시)
  const preview = useConditionsPreview(device, sess, loaded, data.previewByStep[step - 1]);

  const patch = (p: Partial<DeviceConditions>) => setDevice((d) => ({ ...d, ...p }));
  const patchSess = (p: Partial<SessionConditions>) => setSess((v) => ({ ...v, ...p }));

  /** 글자·선택 칸 연결: value + onChange */
  const field = (key: TextKey) => ({
    value: device[key],
    onChange: (e: { target: { value: string } }) => patch({ [key]: e.target.value }),
  });
  const sessionField = (key: SessionTextKey) => ({
    value: sess[key] ?? "",
    onChange: (e: { target: { value: string } }) => patchSess({ [key]: e.target.value }),
  });

  /** 1단계를 넘어가려면 생년월일이 맞아야 해요. 막히면 1단계에 남아 이유를 보여 줘요 */
  const canLeaveStep1 = () => {
    const ok = birthProblem(device.birth) === null;
    if (!ok) {
      setBirthBlocked(true);
      setStep(1);
    }
    return ok;
  };

  return {
    data,
    step,
    goTo: (n: number) => {
      if (n > 1 && !canLeaveStep1()) return;
      setStep(n);
    },
    prev: () => setStep((s) => Math.max(1, s - 1)),
    next: () => {
      if (step === 1 && !canLeaveStep1()) return;
      setStep((s) => Math.min(3, s + 1));
    },
    birthBlocked,
    isLast: step === 3,
    preview,
    field,
    sessionField,
    /** 사는 곳 시·도를 바꾸면 시·군·구는 다시 골라요 */
    /** 사는 곳 코드. 시·도만 고르면 2자리, 시·군·구까지 고르면 5자리 */
    regionCode: device.regionCode,
    setRegionCode: (regionCode: string) => patch({ regionCode }),
    /** 찾아볼 지역 코드 (한 곳). 고르면 바로 값이 돼요. 안 고르면 "" (전체 지역) */
    searchRegionCode: device.searchRegionCodes[0] ?? "",
    setSearchRegionCode: (code: string) => patch({ searchRegionCodes: code ? [code] : [] }),
    head: device.head,
    setHead: (head: Head) => patch({ head }),
    marry: device.marry,
    setMarry: (marry: Marry) => patch({ marry }),
    kids: device.kids,
    /** 함께 사는 가족 수. 모르면 null (예전 「4명 이상」은 다시 골라야 해요) */
    household: householdCount(device.householdSize),
    householdDown: () =>
      setDevice((d) => {
        const n = householdCount(d.householdSize);
        return {
          ...d,
          householdSize: `${Math.max(MIN_HOUSEHOLD, (n ?? MIN_HOUSEHOLD + 1) - 1)}명`,
        };
      }),
    householdUp: () =>
      setDevice((d) => {
        const n = householdCount(d.householdSize);
        return {
          ...d,
          householdSize: `${n === null ? MIN_HOUSEHOLD : Math.min(MAX_HOUSEHOLD, n + 1)}명`,
        };
      }),
    kidsDown: () => setDevice((d) => ({ ...d, kids: Math.max(0, d.kids - 1) })),
    kidsUp: () => setDevice((d) => ({ ...d, kids: Math.min(9, d.kids + 1) })),
    prios: device.priorities,
    togglePrio: (p: string) => setDevice((d) => ({ ...d, priorities: toggle(d.priorities, p) })),
    statuses: device.statuses,
    toggleStatus: (s: string) => setDevice((d) => ({ ...d, statuses: toggle(d.statuses, s) })),
    assetUnknown: sess.assetUnknown,
    setAssetUnknown: (assetUnknown: boolean) => patchSess({ assetUnknown }),
    noCar: sess.noCar ?? false,
    setNoCar: (noCar: boolean) => patchSess({ noCar }),
    rankChecks: sess.rankChecks,
    toggleRankCheck: (key: string) =>
      setSess((v) => ({ ...v, rankChecks: toggle(v.rankChecks, key) })),
    estimatedRank: estimateRank(data.rankCriteria, sess.rankChecks),
    saveOnDevice: stored.status === "ready" ? stored.saveOnDevice : true,
    setSaveOnDevice,
    hasSaved: stored.status === "ready" && stored.device !== null,
    clearSaved: () => {
      clearConditions();
      setDevice(defaultDevice(data));
      setSess(emptySession);
    },
    /** 확인하기: 저장하고 결과(홈, 또는 ?next로 받은 곳)로 */
    submit: () => {
      if (!canLeaveStep1()) return;
      saveConditions(device, sess);
      router.push(next);
    },
  };
}

export type ProfileForm = ReturnType<typeof useProfileForm>;
