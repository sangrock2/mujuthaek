"use client";

import { useSyncExternalStore } from "react";
import { snapshotRegions } from "@/lib/regions";
import type { ConditionsSnapshot, DeviceConditions, SessionConditions } from "./types";
import { track } from "@/lib/analytics";

const DEVICE_KEY = "mujuthaek:conditions:v1";
const SAVE_PREF_KEY = "mujuthaek:save-on-device";
const SESSION_DEVICE_KEY = "mujuthaek:conditions:device-session";
const SESSION_KEY = "mujuthaek:conditions:session";

/** 이 기기에 저장한 조건은 30일 뒤 지워요 */
export const DEVICE_TTL_MS = 30 * 24 * 60 * 60 * 1000;

const LOADING: ConditionsSnapshot = { status: "loading" };

type Stored = { savedAt: number; data: DeviceConditions };

// 사파리 프라이빗 모드처럼 저장소를 못 쓰면 메모리에만 둬요
const memory = new Map<string, string>();

function read(storage: () => Storage, key: string): string | null {
  try {
    return storage().getItem(key);
  } catch {
    return memory.get(key) ?? null;
  }
}

function write(storage: () => Storage, key: string, value: string | null) {
  try {
    if (value === null) storage().removeItem(key);
    else storage().setItem(key, value);
  } catch {
    if (value === null) memory.delete(key);
    else memory.set(key, value);
  }
}

const local = () => window.localStorage;
const session = () => window.sessionStorage;

function parse<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

type LegacyPlace = { sido: string; sigungu: string };
type LegacyDevice = Partial<{
  sido: string;
  sigungu: string;
  searchRegions: LegacyPlace[];
  /** 예전 조건 입력의 직장 · 학교 위치 (지금은 받지 않아요) */
  workplace: string;
}>;

/**
 * 예전 조건 정리: 이름으로 저장한 지역 → 코드, 지금은 받지 않는 칸(직장 위치)은 버려요. 찾아볼 지역은 한 곳만 (예전엔 3곳까지).
 * 예전 가구원 수 「4명 이상」은 4명인지 그보다 많은지 몰라서 비워요 (다시 고를 때까지 소득 조건은 확인 필요)
 */
function migrateDevice(raw: DeviceConditions & LegacyDevice): DeviceConditions {
  const { sido, sigungu, searchRegions, ...rest } = raw;
  delete rest.workplace;
  if (typeof rest.householdSize === "string" && rest.householdSize.includes("이상")) {
    rest.householdSize = "";
  }
  if (typeof rest.regionCode === "string" && Array.isArray(rest.searchRegionCodes))
    return { ...rest, searchRegionCodes: rest.searchRegionCodes.slice(0, 1) };
  const toCode = (p: LegacyPlace) => snapshotRegions.codeByNames(p.sido, p.sigungu);
  return {
    ...rest,
    regionCode: (sido && toCode({ sido, sigungu: sigungu ?? "" })) || "",
    searchRegionCodes: (searchRegions ?? [])
      .map(toCode)
      .filter((c): c is string => Boolean(c))
      .slice(0, 1),
  };
}

function readSnapshot(): ConditionsSnapshot {
  const saveOnDevice = read(local, SAVE_PREF_KEY) !== "false";
  let device: DeviceConditions | null = null;
  let savedAt: number | null = null;

  if (saveOnDevice) {
    const stored = parse<Stored>(read(local, DEVICE_KEY));
    if (stored && Date.now() - stored.savedAt > DEVICE_TTL_MS) {
      write(local, DEVICE_KEY, null);
    } else if (stored) {
      device = stored.data;
      savedAt = stored.savedAt;
    }
  } else {
    device = parse<DeviceConditions>(read(session, SESSION_DEVICE_KEY));
  }
  if (device) device = migrateDevice(device);

  return {
    status: "ready",
    device,
    session: parse<SessionConditions>(read(session, SESSION_KEY)),
    saveOnDevice,
    savedAt,
  };
}

let snapshot: ConditionsSnapshot | null = null;
const listeners = new Set<() => void>();

function emit() {
  snapshot = readSnapshot();
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  // 다른 탭에서 바꾸거나 지운 것도 반영해요
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key.startsWith("mujuthaek:")) emit();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function getSnapshot() {
  if (!snapshot) snapshot = readSnapshot();
  return snapshot;
}

/** PC/모바일 화면이 같이 떠 있어도 같은 값을 보도록 한곳에서 읽어요. 서버와 첫 렌더는 loading */
export function useConditions(): ConditionsSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, () => LOADING);
}

export function saveConditions(device: DeviceConditions, sessionValues: SessionConditions) {
  track("conditions_complete"); // 방문 통계: 값은 보내지 않아요
  const saveOnDevice = read(local, SAVE_PREF_KEY) !== "false";
  if (saveOnDevice) {
    write(
      local,
      DEVICE_KEY,
      JSON.stringify({ savedAt: Date.now(), data: device } satisfies Stored),
    );
    write(session, SESSION_DEVICE_KEY, null);
  } else {
    write(session, SESSION_DEVICE_KEY, JSON.stringify(device));
  }
  write(session, SESSION_KEY, JSON.stringify(sessionValues));
  emit();
}

/** 이 기기 저장을 켜고 끄기. 끄면 이 기기에 저장한 조건은 지우고 이번 탭에서만 써요 */
export function setSaveOnDevice(on: boolean) {
  const current = getSnapshot();
  const device = current.status === "ready" ? current.device : null;
  write(local, SAVE_PREF_KEY, on ? null : "false");
  if (on) {
    if (device) {
      write(
        local,
        DEVICE_KEY,
        JSON.stringify({ savedAt: Date.now(), data: device } satisfies Stored),
      );
    }
    write(session, SESSION_DEVICE_KEY, null);
  } else {
    write(local, DEVICE_KEY, null);
    if (device) write(session, SESSION_DEVICE_KEY, JSON.stringify(device));
  }
  emit();
}

/** 저장한 조건 모두 지우기 (이 기기 + 이번 탭) */
export function clearConditions() {
  write(local, DEVICE_KEY, null);
  write(session, SESSION_DEVICE_KEY, null);
  write(session, SESSION_KEY, null);
  emit();
}
