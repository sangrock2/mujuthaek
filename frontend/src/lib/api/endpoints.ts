// 백엔드 경로 (mujuthaek-be services/api). 아직 없는 API는 설계 문서 경로로 둬요
export const endpoints = {
  authRefresh: "/api/auth/refresh",
  authLogout: "/api/auth/logout",
  /** 내 정보. 로그인하지 않았으면 401 (로그인 여부 확인에도 써요) */
  usersMe: "/api/users/me",
  /** 연락용 이메일 등록·변경(PUT {email, consentVersion}) · 삭제(DELETE). 둘 다 204 */
  usersMeEmail: "/api/users/me/email",
  regions: "/api/v1/regions",
  /** 판정 기준값 (기준 소득 월액, 자산·자동차 구간 경계, 순위 요건) */
  eligibilityCriteria: "/api/v1/eligibility/criteria",
  /** 맞춤 목록: 필터 + 판정 입력(구간 값)을 보내면 판정 결과가 붙은 공고 목록 */
  noticesSearch: "/api/v1/notices/search",
  /** 지도: 범위 안 공고 핀 (많으면 지역 묶음). 공개 정보라 판정은 없어요 */
  noticesMap: "/api/v1/notices/map",
  /** 혜택 맞춤 목록: 찾아볼 지역 + 판정 입력(구간 값) → 판정 결과가 붙은 혜택 */
  benefitsSearch: "/api/v1/benefits/search",
  /** 혜택 상세 (공개 정보) */
  benefitDetail: (id: string) => `/api/v1/benefits/${encodeURIComponent(id)}`,
  /** 혜택 하나의 판정 (조건 그룹별 결과) */
  benefitEvaluate: (id: string) => `/api/v1/benefits/${encodeURIComponent(id)}/evaluate`,
  /** 홈 요약: 내 조건으로 판정한 공고 개수 · 새 공고 · 마감 임박 · 생활권 */
  homeSummary: "/api/v1/home/summary",
  /** 공고 상세 (공개 정보) */
  noticeDetail: (id: string) => `/api/v1/notices/${encodeURIComponent(id)}`,
  /** 공고 주택목록 (호별, 커서) */
  noticeUnits: (id: string) => `/api/v1/notices/${encodeURIComponent(id)}/units`,
  /** 사업공간 맞춤 목록: 판정 입력(사는 곳 · 사업 입력) → 공간마다 판정, 종류별 개수 */
  spacesSearch: "/api/v1/spaces/search",
  /** 사업공간 하나의 판정 (상세 내용은 noticeDetail) */
  spaceEvaluate: (id: string) => `/api/v1/spaces/${encodeURIComponent(id)}/evaluate`,
  /** 사업 지원(창업지원 사업) 맞춤 목록: 판정 입력 → 사업마다 판정, 종류별 개수 */
  supportsSearch: "/api/v1/supports/search",
  /** 사업 지원 하나의 판정 (상세 API가 없어서 기간 · 지역 · 자격 조건도 여기서) */
  supportEvaluate: (id: string) => `/api/v1/supports/${encodeURIComponent(id)}/evaluate`,
  /** 단지 하나의 생활권 (항목 점수 · 가까운 시설 · 세권 태그). 공개 정보 */
  areaSite: (siteId: string) => `/api/v1/areas/sites/${encodeURIComponent(siteId)}`,
  /** 공고 하나의 판정 (조건별 결과) */
  noticeEvaluate: (id: string) => `/api/v1/eligibility/notices/${encodeURIComponent(id)}/evaluate`,
  /** 웹 푸시 기기 등록(PUT)·해제(DELETE). 본문은 subscription.toJSON() 그대로 */
  pushSubscriptions: "/api/users/me/push-subscriptions",
  /** 알림을 봤는지·눌렀는지 알리기 (/{id}/shown · /{id}/clicked, 로그인 없이) */
  notificationEvents: "/api/v1/notifications",
  /** 웹 푸시 VAPID 공개키 (로그인 없이) */
  pushPublicKey: "/api/v1/push/public-key",
  /** 알림함: 목록(GET ?cursor&size&unread) · /unread-count · /{id}/read · /read-all */
  notifications: "/api/users/me/notifications",
  notificationSettings: "/api/users/me/notification-settings",
  /** 읽지 않은 알림 수 {count} */
  notificationsUnreadCount: "/api/users/me/notifications/unread-count",
  /** 관심 공고: 목록(GET ?targetType&cursor&size) */
  favorites: "/api/users/me/favorites",
  /** 관심 공고 저장(PUT)·지우기(DELETE). type: notice · benefit · startup-support · space-recruitment */
  favorite: (type: string, id: string) =>
    `/api/users/me/favorites/${encodeURIComponent(type)}/${encodeURIComponent(id)}`,
  /** 관심 조건 GET·PUT·DELETE. kind: housing · business · support */
  interests: (kind: "housing" | "business" | "support") => `/api/users/me/interests/${kind}`,
  /** 내 제보 (공고·혜택·사업·생활권·일반, 최근 100건) */
  myReports: "/api/users/me/reports",
  /** 회원 탈퇴 시작 → {reauthUrl} 로 이동 */
  withdrawal: "/api/users/me/withdrawal",
  /** 일반 제보 (공고에 묶이지 않은 제보) */
  generalReports: "/api/v1/reports",
  /** 공고 · 혜택 · 창업지원 사업(사업공간 포함) 제보 */
  noticeReports: (id: string) => `/api/v1/notices/${encodeURIComponent(id)}/reports`,
  benefitReports: (id: string) => `/api/v1/benefits/${encodeURIComponent(id)}/reports`,
  programReports: (id: string) => `/api/v1/programs/${encodeURIComponent(id)}/reports`,
  /** 공고 채팅방 정보 {noticeId, readOnly, readOnlyFrom, guide}. 방 = 공고 (로그인 없이) */
  noticeChat: (id: string) => `/api/v1/notices/${encodeURIComponent(id)}/chat`,
  /** 채팅 목록(GET ?cursor&size, 최신순) · 보내기(POST {content, parentId?}) */
  noticeChatMessages: (id: string) => `/api/v1/notices/${encodeURIComponent(id)}/chat/messages`,
  /** 채팅 실시간 받기 (SSE, 로그인 없이 EventSource로) */
  noticeChatStream: (id: string) => `/api/v1/notices/${encodeURIComponent(id)}/chat/stream`,
  /** 내 메시지 지우기(DELETE) */
  chatMessage: (id: string) => `/api/v1/chat/messages/${encodeURIComponent(id)}`,
  /** 좋아요(PUT) · 취소(DELETE) → {messageId, likeCount, liked} */
  chatMessageLike: (id: string) => `/api/v1/chat/messages/${encodeURIComponent(id)}/like`,
  /** 메시지 신고 {reason, detail?} */
  chatMessageReports: (id: string) => `/api/v1/chat/messages/${encodeURIComponent(id)}/reports`,
} as const;
