import { pathSegment } from "./api/path";
import { safeAppPath } from "./safeUrl";

// 디자인 파일(X.dc.html) → 라우트
export const routes = {
  main: "/",
  login: "/login",
  /** 처음 간편 로그인한 뒤 약관 동의 (가입 마무리) */
  signup: "/signup",
  /** 간편 로그인 뒤 돌아오는 곳 (백엔드가 보내요) */
  authCallback: "/auth/callback",
  welcome: "/welcome",
  /** 회원 탈퇴를 마친 뒤 (백엔드가 보내요) */
  withdrawn: "/withdrawn",
  profile: "/profile",
  home: "/home",
  benefits: "/benefits",
  benefit: (id: string) => `/benefits/${pathSegment(id)}`,
  homes: "/homes",
  notice: (id: string) => `/notices/${pathSegment(id)}`,
  score: "/score",
  /** 대출 자격 확인 (정확한 소득·순자산을 이 화면에서만 넣어요) */
  loans: "/loans",
  alerts: "/alerts",
  me: "/me",
  preparations: "/me/preparations",
  preparation: (id: string) => `/me/preparations/${pathSegment(id)}`,
  search: "/search",
  business: "/business",
  bizOnboarding: "/business/onboarding",
  space: (id: string) => `/business/spaces/${pathSegment(id)}`,
  bizSupport: "/business/support",
  announcements: "/announcements",
  faq: "/faq",
  terms: "/terms",
  privacy: "/privacy",
  legal: "/legal",
  install: "/install",
  /** 「무주택자들은 어떻게 만들었나요」 소개 */
  howItWorks: "/how-it-works",
  admin: "/admin",
  adminReview: "/admin/review",
  adminExtraction: "/admin/extraction",
  adminSources: "/admin/sources",
  adminCriteria: "/admin/criteria",
  adminReports: "/admin/reports",
  adminTraffic: "/admin/traffic",
  adminUsers: "/admin/users",
  adminActivity: "/admin/activity",
} as const;

export type Mode = "home" | "business";

/** 조건 입력 뒤 돌아갈 곳을 붙인 조건 입력 주소 (예: /homes에서 「조건 수정」) */
export const profileThen = (next: string) => `${routes.profile}?next=${encodeURIComponent(next)}`;

/** URL 파서가 탭·줄바꿈을 제거한 뒤 외부 주소가 되지 않게 공통 앱 경로 검증을 써요. */
export function safeNext(value: string | null | undefined): string | null {
  return safeAppPath(value);
}
