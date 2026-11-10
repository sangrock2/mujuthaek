// 관리자 권한. 일반 관리자는 받은 권한만큼만 관리 화면을 써요. 최상위 관리자는 모두 가진 것으로 봐요.
// 실제 확인은 서버가 요청마다 해요(백엔드 SecurityConfig·AdminUserService). 화면은 메뉴·버튼을 고르는 데만 써요.
import { routes } from "@/lib/routes";

export type AdminPermission =
  | "NOTICE_REVIEW"
  | "BENEFIT_REVIEW"
  | "SOURCES"
  | "CRITERIA"
  | "REPORTS"
  | "CHAT"
  | "USERS_VIEW"
  | "USERS_SUSPEND"
  | "ADMIN_APPOINT"
  | "PERMISSION_GRANT"
  | "PERMISSION_REVOKE"
  | "TRAFFIC"
  | "ACTIVITY";

export const PERMISSION_INFO: Record<AdminPermission, { label: string; desc: string }> = {
  NOTICE_REVIEW: { label: "공고 검수", desc: "공고 추출 결과 승인·반려·수정·다시 열기" },
  BENEFIT_REVIEW: { label: "혜택 검수", desc: "혜택 정책 승인·반려·수정·다시 열기" },
  SOURCES: { label: "수집 출처", desc: "출처 일시 중지·재개·즉시 수집" },
  CRITERIA: { label: "판정 기준", desc: "중위소득·도시근로자 소득·순위 기준값, 규제지역" },
  REPORTS: { label: "제보 처리", desc: "공고·혜택·창업 사업 제보, 생활권 제보" },
  CHAT: { label: "채팅 제재", desc: "채팅 신고 메시지 계속 가리기·되돌리기" },
  USERS_VIEW: { label: "회원 보기", desc: "회원 목록·찾기" },
  USERS_SUSPEND: { label: "이용 정지", desc: "회원 이용 정지·해제" },
  ADMIN_APPOINT: { label: "관리자 지정", desc: "일반 회원을 일반 관리자로 지정·해제" },
  PERMISSION_GRANT: {
    label: "권한 부여",
    desc: "내가 가진 권한을 다른 관리자에게 주기 · 이 권한은 최상위만 주고 빼요",
  },
  PERMISSION_REVOKE: {
    label: "권한 박탈",
    desc: "내가 가진 권한을 다른 관리자에게서 빼기 · 이 권한은 최상위만 주고 빼요",
  },
  TRAFFIC: { label: "트래픽 보기", desc: "GA·서버 방문 통계, 봇, 알림 지표" },
  ACTIVITY: { label: "처리 기록 보기", desc: "모든 관리자의 처리 기록" },
};

export const PERMISSION_GROUPS: { label: string; items: AdminPermission[] }[] = [
  { label: "공고", items: ["NOTICE_REVIEW", "BENEFIT_REVIEW", "SOURCES", "CRITERIA"] },
  { label: "신고", items: ["REPORTS", "CHAT"] },
  {
    label: "회원",
    items: [
      "USERS_VIEW",
      "USERS_SUSPEND",
      "ADMIN_APPOINT",
      "PERMISSION_GRANT",
      "PERMISSION_REVOKE",
    ],
  },
  { label: "기록", items: ["TRAFFIC", "ACTIVITY"] },
];

export const ALL_PERMISSIONS = PERMISSION_GROUPS.flatMap((g) => g.items);

/** 권한을 다루는 권한: 이 둘을 주고 빼는 일과 이 둘을 가진 관리자를 바꾸는 일은 최상위만 */
export const MANAGING: AdminPermission[] = ["PERMISSION_GRANT", "PERMISSION_REVOKE"];

/** 자주 쓰는 묶음 (누르면 체크만 바뀌고, 저장은 권한 하나하나로 해요) */
export const PERMISSION_PRESETS: { label: string; items: AdminPermission[] }[] = [
  { label: "공고 관리자", items: ["NOTICE_REVIEW", "BENEFIT_REVIEW", "SOURCES"] },
  { label: "신고 관리자", items: ["REPORTS", "CHAT"] },
  { label: "회원 관리자", items: ["USERS_VIEW", "USERS_SUSPEND", "ADMIN_APPOINT"] },
  {
    label: "부여·박탈 빼고 전부",
    items: ALL_PERMISSIONS.filter((p) => !MANAGING.includes(p)),
  },
];

/** 관리자 화면 경로별로 필요한 권한 (하나라도 있으면). 없는 경로(개요)는 관리자 누구나 */
export const ROUTE_PERMISSIONS: Record<string, AdminPermission[]> = {
  [routes.adminReview]: ["NOTICE_REVIEW", "BENEFIT_REVIEW"],
  [routes.adminSources]: ["SOURCES"],
  [routes.adminCriteria]: ["CRITERIA"],
  [routes.adminReports]: ["REPORTS", "CHAT"],
  [routes.adminTraffic]: ["TRAFFIC"],
  [routes.adminUsers]: [
    "USERS_VIEW",
    "USERS_SUSPEND",
    "ADMIN_APPOINT",
    "PERMISSION_GRANT",
    "PERMISSION_REVOKE",
  ],
  [routes.adminActivity]: ["ACTIVITY"],
};

/** 그 경로를 열 수 있는지 */
export function canOpen(permissions: readonly AdminPermission[], href: string) {
  const need = ROUTE_PERMISSIONS[href];
  return !need || need.some((p) => permissions.includes(p));
}
