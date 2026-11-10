// 관리자 「회원」 화면 타입과 예시 데이터. 실제 값은 GET /api/admin/users (백엔드 user 모듈)
import type { AdminPermission } from "@/features/admin/permissions";

/** 일반 회원 · 일반 관리자 · 최상위 관리자(1명) */
export type AdminUserRole = "USER" | "ADMIN" | "SUPER_ADMIN";

export type Suspension = {
  reason: string;
  /** 비어 있으면 해제할 때까지 */
  until: string | null;
  at: string;
};

export type AdminUser = {
  id: string;
  nickname: string | null;
  role: AdminUserRole;
  /** 이어진 소셜 로그인 (KAKAO·NAVER·GOOGLE) */
  providers: string[];
  joinedAt: string;
  lastLoginAt: string | null;
  /** 일반 관리자가 받은 권한 (최상위는 전부라 비어 있어요) */
  permissions: AdminPermission[];
  /** 지금 이용 정지 중이면 그 내용 */
  suspension: Suspension | null;
};

export type AdminUsersPage = { items: AdminUser[]; total: number };

/** 회원 찾기 거르기: 전체 · 관리자(일반·최상위) · 일반 회원 · 정지 중 */
export type AdminUserFilter = "" | "ADMIN" | "USER" | "SUSPENDED";

export type AdminUserName = { id: string; nickname: string | null; role: AdminUserRole };

export type AdminChangeKind =
  | "APPOINT"
  | "DISMISS"
  | "GRANT"
  | "REVOKE"
  | "SUSPEND"
  | "UNSUSPEND"
  | "TRANSFER"
  | "FREEZE"
  | "UNFREEZE";

/** 관리자 변경 기록 한 줄 (GET /api/admin/users/changes) */
export type AdminChange = {
  id: number;
  changedAt: string;
  kind: AdminChangeKind;
  /** GRANT·REVOKE의 권한 */
  permission: AdminPermission | null;
  /** 해제 때 빠진 권한, 정지 이유, 긴급 정지 이유 */
  note: string | null;
  /** 대상 회원 (긴급 정지는 null) */
  userId: string | null;
  nickname: string | null;
  changedBy: string | null;
  changedByNickname: string | null;
};

const SUPER = "01a17000-0000-7000-8000-00000000ad01";

export const adminUsersMock: AdminUser[] = [
  {
    id: SUPER,
    nickname: "김○○",
    role: "SUPER_ADMIN",
    providers: ["KAKAO"],
    joinedAt: "2026-10-01T00:00:00Z",
    lastLoginAt: "2026-10-27T01:00:00Z",
    permissions: [],
    suspension: null,
  },
  {
    id: "01a17000-0000-7000-8000-00000000ad02",
    nickname: "공고 담당",
    role: "ADMIN",
    providers: ["NAVER"],
    joinedAt: "2026-10-05T00:00:00Z",
    lastLoginAt: "2026-10-26T09:00:00Z",
    permissions: ["NOTICE_REVIEW", "BENEFIT_REVIEW", "SOURCES"],
    suspension: null,
  },
  {
    id: "01a17000-0000-7000-8000-000000000b01",
    nickname: "이청년",
    role: "USER",
    providers: ["GOOGLE"],
    joinedAt: "2026-10-20T00:00:00Z",
    lastLoginAt: "2026-10-26T12:00:00Z",
    permissions: [],
    suspension: null,
  },
  {
    id: "01a17000-0000-7000-8000-000000000b02",
    nickname: "박신혼",
    role: "USER",
    providers: ["NAVER", "KAKAO"],
    joinedAt: "2026-10-22T00:00:00Z",
    lastLoginAt: null,
    permissions: [],
    suspension: { reason: "채팅 도배", until: "2026-11-03T00:00:00Z", at: "2026-10-27T00:00:00Z" },
  },
];

export const adminChangesMock: AdminChange[] = [
  {
    id: 3,
    changedAt: "2026-10-27T00:00:00Z",
    kind: "SUSPEND",
    permission: null,
    note: "채팅 도배",
    userId: "01a17000-0000-7000-8000-000000000b02",
    nickname: "박신혼",
    changedBy: SUPER,
    changedByNickname: "김○○",
  },
  {
    id: 2,
    changedAt: "2026-10-25T05:01:00Z",
    kind: "GRANT",
    permission: "NOTICE_REVIEW",
    note: null,
    userId: "01a17000-0000-7000-8000-00000000ad02",
    nickname: "공고 담당",
    changedBy: SUPER,
    changedByNickname: "김○○",
  },
  {
    id: 1,
    changedAt: "2026-10-25T05:00:00Z",
    kind: "APPOINT",
    permission: null,
    note: null,
    userId: "01a17000-0000-7000-8000-00000000ad02",
    nickname: "공고 담당",
    changedBy: SUPER,
    changedByNickname: "김○○",
  },
];
