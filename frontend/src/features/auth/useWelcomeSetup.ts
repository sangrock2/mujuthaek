"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { usePush } from "@/features/alerts/usePush";
import { useConditions } from "@/features/conditions/store";
import { interestKey, toInterestRegion, type InterestKind } from "@/features/me/api";
import { api } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";
import { useRegions } from "@/features/regions/queries";

export const interestOptions = ["청약 · 공공임대", "정부 혜택", "전월세", "사업공간"] as const;

/**
 * 고른 관심 분야 → 저장할 관심 조건 (없으면 그 종류는 지워요). 전월세만 고르면 월세·전세 대출만.
 * regionCode는 사용자가 「사는 지역도 관심 지역으로 저장」을 켰을 때만 넘어와요
 */
export function interestBodies(chosen: string[], regionCode: string) {
  const regions = regionCode ? [toInterestRegion(regionCode)] : [];
  const base = { regionCodes: regions, includeNationwide: true };
  const support = chosen.includes("정부 혜택")
    ? { ...base, supportKinds: [] }
    : chosen.includes("전월세")
      ? { ...base, supportKinds: ["RENT", "DEPOSIT_LOAN"] }
      : null;
  return {
    housing: chosen.includes("청약 · 공공임대") ? { ...base, noticeTypes: [] } : null,
    support,
    business: chosen.includes("사업공간")
      ? { ...base, industryCodes: [], startupStages: [] }
      : null,
  } satisfies Record<InterestKind, object | null>;
}

/**
 * 가입 완료 화면의 첫 설정 3가지 (PC/모바일 공통). 관심 분야는 고를 때마다 관심 조건으로 저장해요(새 공고 알림).
 * 사는 지역은 이 기기에만 저장한 값이라, 화면에서 알리고 사용자가 켰을 때만 관심 지역으로 계정(서버)에 올려요
 * (예전에는 알리지 않고 올렸어요, 2026-11-16 보안 감사 4장)
 */
export function useWelcomeSetup() {
  // 마감 알림은 이 브라우저의 웹 푸시 구독이에요. 예전에는 켜짐 모양만 바꾸고 구독하지 않았어요(2026-10-29)
  const push = usePush();
  const alert = push.enabled;
  const [interests, setInterests] = useState<string[]>([]);
  const [cond, setCond] = useState(false);
  const [shareRegion, setShareRegion] = useState(false);
  const conditions = useConditions();
  const regions = useRegions();
  const client = useQueryClient();
  const deviceRegion = conditions.status === "ready" ? (conditions.device?.regionCode ?? "") : "";
  const interestDone = interests.length > 0;
  const done = [alert, interestDone, cond].filter(Boolean).length;

  const save = (chosen: string[], share = shareRegion) => {
    if (USE_MOCKS) return;
    const bodies = interestBodies(chosen, share ? deviceRegion : "");
    for (const kind of Object.keys(bodies) as InterestKind[]) {
      const body = bodies[kind];
      const done = body
        ? api.put(endpoints.interests(kind), body)
        : api.delete(endpoints.interests(kind));
      void done
        .then(() => client.invalidateQueries({ queryKey: interestKey(kind) }))
        .catch(() => undefined); // 저장하지 못해도 내 정보 → 관심 조건에서 다시 고를 수 있어요
    }
  };

  return {
    alert,
    /** 켜면 브라우저 알림 허용을 묻고 구독해요. 실패하면 꺼진 채로 alertError에 이유를 남겨요 */
    setAlert: (on: boolean) => void (on ? push.turnOn() : push.turnOff()),
    alertError: push.error,
    alertPending: push.pending,
    interests,
    interestDone,
    toggleInterest: (label: string) => {
      const next = interests.includes(label)
        ? interests.filter((x) => x !== label)
        : [...interests, label];
      setInterests(next);
      save(next);
    },
    /** 이 기기에 저장한 사는 지역 (없으면 "") · 화면에 보일 이름 */
    deviceRegion,
    deviceRegionLabel: deviceRegion ? regions.label(deviceRegion) : "",
    /** 사는 지역을 관심 지역으로 계정에 저장할지 (기본은 끔) */
    shareRegion,
    setShareRegion: (on: boolean) => {
      setShareRegion(on);
      // 이미 고른 분야가 있으면 바뀐 지역으로 다시 저장해요 (끄면 지역 없이 전국으로)
      if (interests.length > 0) save(interests, on);
    },
    cond,
    confirmCond: () => setCond(true),
    done,
    progress: `${Math.round((done / 3) * 100)}%`,
  };
}
