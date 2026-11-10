"use client";

// 내 정보 화면의 실제 API: 알림 설정 · 관심 조건 · 제보 · 회원 탈퇴
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/features/auth/session";
import { API_BASE_URL, api, ApiError } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";

/* ── 알림 설정 (GET·PUT /api/users/me/notification-settings) ───────────── */

/** 백엔드 NotificationSettings. 꺼도 알림함에는 남고 푸시만 안 가요 */
export type NotificationSettings = {
  newNotice: boolean;
  newSupport: boolean;
  deadline: boolean;
  correction: boolean;
  followUp: boolean;
  quietEnabled: boolean;
};

const DEFAULT_SETTINGS: NotificationSettings = {
  newNotice: true,
  newSupport: true,
  deadline: true,
  correction: true,
  followUp: true,
  quietEnabled: false,
};

const settingsKey = ["me", "notification-settings"] as const;

export function useNotificationSettings() {
  const session = useSession();
  const client = useQueryClient();
  const loggedIn = !!session.data;
  const q = useQuery({
    queryKey: settingsKey,
    queryFn: () => api.get<NotificationSettings>(endpoints.notificationSettings),
    enabled: !USE_MOCKS && loggedIn,
    retry: false,
  });
  const save = useMutation({
    mutationFn: (next: NotificationSettings) =>
      USE_MOCKS
        ? Promise.resolve(next)
        : api.put<NotificationSettings>(endpoints.notificationSettings, next),
    onMutate: (next) => {
      const before = client.getQueryData<NotificationSettings>(settingsKey);
      client.setQueryData(settingsKey, next);
      return { before };
    },
    onError: (_e, _next, ctx) => client.setQueryData(settingsKey, ctx?.before),
    onSuccess: (saved) => client.setQueryData(settingsKey, saved),
  });
  const value =
    (USE_MOCKS ? client.getQueryData<NotificationSettings>(settingsKey) : q.data) ??
    DEFAULT_SETTINGS;
  return {
    value,
    loading: !USE_MOCKS && loggedIn && q.isPending,
    loggedIn: USE_MOCKS || loggedIn,
    failed: save.isError,
    set: (patch: Partial<NotificationSettings>) => save.mutate({ ...value, ...patch }),
    /** 저장이 끝날 때까지 기다려요 (실패하면 throw, 화면 값은 되돌아가요) */
    setAsync: (patch: Partial<NotificationSettings>) => save.mutateAsync({ ...value, ...patch }),
  };
}

/* ── 관심 조건 (GET·PUT·DELETE /api/users/me/interests/{kind}) ─────────── */

export type InterestKind = "housing" | "business" | "support";

/** 백엔드 관심 조건. 목록이 비면 「모두」, saved=false면 아직 저장 안 함(새 공고 알림이 안 가요) */
export type Interest = {
  saved: boolean;
  regionCodes: string[];
  includeNationwide: boolean;
  noticeTypes?: string[];
  industryCodes?: string[];
  startupStages?: string[];
  supportKinds?: string[];
};

/** 화면의 지역 코드(시·도 2자리 · 시군구 5자리) → 백엔드 코드(시·도 전체는 xx000) */
export const toInterestRegion = (code: string) => (code.length === 2 ? `${code}000` : code);
/** 백엔드 코드 → 화면의 지역 코드 */
export const fromInterestRegion = (code: string) =>
  code.endsWith("000") ? code.slice(0, 2) : code;

export const interestKey = (kind: InterestKind) => ["me", "interests", kind] as const;

const EMPTY_INTEREST: Interest = { saved: false, regionCodes: [], includeNationwide: true };

export function useInterest(kind: InterestKind) {
  const session = useSession();
  const client = useQueryClient();
  const loggedIn = !!session.data;
  const q = useQuery({
    queryKey: interestKey(kind),
    queryFn: () => api.get<Interest>(endpoints.interests(kind)),
    enabled: !USE_MOCKS && loggedIn,
    retry: false,
  });
  const save = useMutation({
    mutationFn: (body: Omit<Interest, "saved">) =>
      USE_MOCKS
        ? Promise.resolve({ ...body, saved: true })
        : api.put<Interest>(endpoints.interests(kind), body),
    onSuccess: (saved) => client.setQueryData(interestKey(kind), saved),
  });
  const remove = useMutation({
    mutationFn: () => (USE_MOCKS ? Promise.resolve(null) : api.delete(endpoints.interests(kind))),
    onSuccess: () => client.setQueryData(interestKey(kind), EMPTY_INTEREST),
  });
  return {
    value: q.data ?? client.getQueryData<Interest>(interestKey(kind)) ?? EMPTY_INTEREST,
    loading: !USE_MOCKS && loggedIn && q.isPending,
    save: save.mutateAsync,
    saving: save.isPending,
    saveFailed: save.isError,
    remove: remove.mutateAsync,
  };
}

/* ── 제보 ─────────────────────────────────────────────────────────── */

/** 일반 제보 종류 (백엔드 field) */
export type GeneralReportKind = "MISSING_NOTICE" | "WRONG_INFO" | "APP_ERROR" | "ETC";

export const generalReportKinds: { key: GeneralReportKind; label: string }[] = [
  { key: "MISSING_NOTICE", label: "빠진 공고·정책" },
  { key: "WRONG_INFO", label: "틀린 정보" },
  { key: "APP_ERROR", label: "화면 오류" },
  { key: "ETC", label: "기타" },
];

/** 대상이 있는 제보: 공고 · 혜택 · 창업지원 사업(사업공간 모집 포함) */
export type ReportTarget = { kind: "notice" | "benefit" | "program"; id: string };

export type ReportBody = {
  field: string;
  currentValue?: string;
  reportedValue?: string;
  note?: string;
  screen?: string;
};

/** 백엔드 제보 오류 → 안내 문구 */
export function reportErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return "로그인하면 제보할 수 있어요";
    if (error.status === 409) return "같은 칸에 보낸 제보를 아직 확인하고 있어요";
    if (error.status === 429) return "제보는 하루에 20건까지 보낼 수 있어요";
    if (error.status === 400) return "내용을 확인해 주세요 (맞는 값이나 설명 중 하나는 필요해요)";
    if (error.status === 404) return "제보할 공고를 찾지 못했어요";
  }
  return "보내지 못했어요. 잠시 뒤 다시 해 주세요";
}

export const myReportsKey = ["me", "reports"] as const;

export async function sendReport(target: ReportTarget | null, body: ReportBody) {
  if (USE_MOCKS) return;
  const path = !target
    ? endpoints.generalReports
    : target.kind === "notice"
      ? endpoints.noticeReports(target.id)
      : target.kind === "benefit"
        ? endpoints.benefitReports(target.id)
        : endpoints.programReports(target.id);
  await api.post(path, body);
}

/** 내 제보 한 줄 (백엔드 MyReportResponse) */
export type MyReport = {
  id: string;
  kind: "NOTICE" | "BENEFIT" | "PROGRAM" | "AREA" | "GENERAL";
  targetId: string | null;
  targetTitle: string | null;
  field: string;
  reportedValue: string | null;
  note: string | null;
  status: "NEW" | "DOING" | "DONE";
  result: "FIXED" | "KEPT" | null;
  reply: string | null;
  createdAt: string;
  handledAt: string | null;
  linkPath: string | null;
};

export function useMyReports() {
  const session = useSession();
  const loggedIn = !!session.data;
  const q = useQuery({
    queryKey: myReportsKey,
    queryFn: () => api.get<{ items: MyReport[] }>(endpoints.myReports).then((r) => r.items),
    enabled: !USE_MOCKS && loggedIn,
    retry: false,
  });
  return {
    items: q.data ?? [],
    loading: !USE_MOCKS && loggedIn && q.isPending,
    /** 불러오지 못했어요(서버 오류·아직 배포 안 됨 등). 예전에는 「보낸 제보가 없어요」로 보여 헷갈렸어요 */
    failed: !USE_MOCKS && loggedIn && q.isError,
    retry: () => void q.refetch(),
    loggedIn,
  };
}

/* ── 회원 탈퇴 ────────────────────────────────────────────────────── */

export type WithdrawalStart = {
  provider: string;
  reauthUrl: string;
  expiresIn: number;
  otherProviders: string[];
};

/**
 * 탈퇴 시작: 본인 확인용 다시 로그인 주소를 받아요. 함께 연결된 다른 소셜(otherProviders)은 서버가 끊을 수 없어서 미리 알려 줘요.
 * 이동은 {@link goWithdrawal}로
 */
export function startWithdrawal(provider?: string) {
  return api.post<WithdrawalStart>(
    `${endpoints.withdrawal}${provider ? `?provider=${encodeURIComponent(provider.toLowerCase())}` : ""}`,
  );
}

/**
 * 다시 로그인 주소로 이동 → 회원 삭제 → /withdrawn. 백엔드가 준 주소는 서버 주소일 수 있어서(Vercel 뒤)
 * 경로만 써서 API 주소(운영은 이 사이트, 로컬은 NEXT_PUBLIC_API_BASE_URL)로 가요
 */
export function goWithdrawal(start: WithdrawalStart) {
  const url = new URL(start.reauthUrl, window.location.origin);
  // 백엔드 OAuth 주소(rewrites로 넘김)라 Next 화면 이동이 아니라 페이지를 새로 열어요
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- Next 화면이 아니라 백엔드로 가는 주소예요
  window.location.href = `${API_BASE_URL}${url.pathname}${url.search}`;
}
