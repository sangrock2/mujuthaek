// 관리자 「트래픽」 화면 타입과 예시 데이터. 실제 값은 GET /api/admin/traffic, /api/admin/traffic/bots (백엔드 traffic 모듈)
export type TrafficItem = { name: string; value: number; users: number };
export type TrafficDaily = {
  date: string;
  activeUsers: number;
  newUsers: number;
  sessions: number;
  pageViews: number;
};
export type FunnelStep = { event: string; label: string; count: number; users: number };
/** 많이 본 공고 한 줄 (제목은 화면이 공고 ID로 찾아요) */
export type NoticeView = { noticeId: string; views: number; users: number };
/** 지금 접속자 (GA 실시간, GET /api/admin/traffic/realtime) */
export type RealtimeData = {
  connected: boolean;
  error: string | null;
  fetchedAt: string | null;
  last30Minutes: number;
  last5Minutes: number;
  devices: TrafficItem[];
};
export type ServerDaily = {
  date: string;
  humanRequests: number;
  botRequests: number;
  humanVisitors: number;
  signups: number;
  logins: number;
  loginFailures: number;
  serverErrors: number;
};

export type TrafficData = {
  asOf: string;
  days: number;
  ga: {
    connected: boolean;
    error: string | null;
    fetchedAt: string | null;
    daily: TrafficDaily[];
    channels: TrafficItem[];
    sources: TrafficItem[];
    campaigns: TrafficItem[];
    landingPages: TrafficItem[];
    pages: TrafficItem[];
    devices: TrafficItem[];
    browsers: TrafficItem[];
    regions: TrafficItem[];
    funnel: FunnelStep[];
    popularNotices: NoticeView[];
  };
  server: ServerDaily[];
};

export type ClientKind = "HUMAN" | "SEARCH_BOT" | "PREVIEW_BOT" | "TOOL" | "MONITOR" | "UNKNOWN";
export type BotAccess = {
  at: string;
  method: string;
  path: string;
  /** 화면 요청(프론트 서버가 넘긴 것)은 응답 코드를 몰라 null */
  status: number | null;
  maskedIp: string | null;
  client: ClientKind;
};
export type BotTrafficData = {
  asOf: string;
  days: number;
  clients: { date: string; client: ClientKind; requests: number }[];
  topSources: {
    maskedIp: string | null;
    key: string | null;
    client: ClientKind;
    requests: number;
    peakPerMinute: number;
    topPath: string;
    firstSeen: string;
    lastSeen: string;
  }[];
  topBotPaths: { path: string; requests: number; humanRequests: number; botRequests: number }[];
  statuses: { group: string; requests: number }[];
  adminAccess: BotAccess[];
  loginFailures: BotAccess[];
};

const DAYS = [
  "2026-10-20",
  "2026-10-21",
  "2026-10-22",
  "2026-10-23",
  "2026-10-24",
  "2026-10-25",
  "2026-10-26",
];
const pick = (values: number[]) => (i: number) => values[i];
const active = pick([182, 205, 231, 198, 164, 241, 120]);
const human = pick([5200, 5800, 6400, 5600, 4700, 6900, 3300]);

export const trafficMock: TrafficData = {
  asOf: "2026-10-26T03:00:00Z",
  days: 7,
  ga: {
    connected: true,
    error: null,
    fetchedAt: "2026-10-26T02:40:00Z",
    daily: DAYS.map((date, i) => ({
      date,
      activeUsers: active(i),
      newUsers: pick([120, 131, 140, 118, 99, 150, 70])(i),
      sessions: pick([240, 268, 301, 260, 210, 322, 160])(i),
      pageViews: pick([910, 1022, 1180, 990, 801, 1270, 610])(i),
    })),
    channels: [
      { name: "Organic Search", value: 820, users: 610 },
      { name: "Direct", value: 410, users: 300 },
      { name: "Organic Social", value: 260, users: 210 },
      { name: "Referral", value: 120, users: 95 },
    ],
    sources: [
      { name: "naver", value: 520, users: 400 },
      { name: "(direct)", value: 410, users: 300 },
      { name: "google", value: 300, users: 210 },
      { name: "kakaotalk", value: 190, users: 160 },
    ],
    campaigns: [{ name: "deadline", value: 88, users: 70 }],
    landingPages: [
      { name: "/", value: 640, users: 500 },
      { name: "/notices/n1", value: 520, users: 410 },
      { name: "/homes", value: 210, users: 170 },
    ],
    pages: [
      { name: "/notices/n1", value: 2900, users: 820 },
      { name: "/", value: 1800, users: 900 },
      { name: "/homes", value: 1200, users: 520 },
    ],
    devices: [
      { name: "mobile", value: 980, users: 980 },
      { name: "desktop", value: 330, users: 330 },
      { name: "tablet", value: 31, users: 31 },
    ],
    browsers: [
      { name: "Chrome", value: 700, users: 700 },
      { name: "Safari", value: 450, users: 450 },
      { name: "Samsung Internet", value: 160, users: 160 },
    ],
    regions: [
      { name: "Seoul", value: 520, users: 520 },
      { name: "Gyeonggi-do", value: 410, users: 410 },
      { name: "Incheon", value: 120, users: 120 },
    ],
    funnel: [
      { event: "session_start", label: "방문", count: 1761, users: 1341 },
      { event: "conditions_complete", label: "조건 입력 완료", count: 402, users: 380 },
      { event: "judgment_run", label: "판정 실행", count: 1210, users: 360 },
      { event: "notice_source_open", label: "원문 보기", count: 530, users: 290 },
      { event: "notice_bookmark", label: "관심 등록", count: 140, users: 120 },
    ],
    popularNotices: [
      { noticeId: "n1", views: 2900, users: 820 },
      { noticeId: "n3", views: 1210, users: 400 },
      { noticeId: "n2", views: 640, users: 260 },
    ],
  },
  server: DAYS.map((date, i) => ({
    date,
    humanRequests: human(i),
    botRequests: pick([900, 1100, 870, 2400, 760, 820, 410])(i),
    humanVisitors: pick([170, 190, 214, 181, 150, 226, 110])(i),
    signups: pick([12, 9, 15, 11, 7, 18, 6])(i),
    logins: pick([80, 91, 104, 88, 70, 112, 51])(i),
    loginFailures: pick([2, 1, 3, 9, 1, 2, 0])(i),
    serverErrors: pick([0, 2, 0, 1, 0, 0, 0])(i),
  })),
};

export const botTrafficMock: BotTrafficData = {
  asOf: "2026-10-26T03:00:00Z",
  days: 7,
  clients: DAYS.flatMap((date, i) => [
    { date, client: "HUMAN" as const, requests: human(i) },
    { date, client: "SEARCH_BOT" as const, requests: pick([500, 620, 480, 510, 420, 470, 230])(i) },
    { date, client: "TOOL" as const, requests: pick([300, 380, 290, 1800, 240, 260, 130])(i) },
    { date, client: "PREVIEW_BOT" as const, requests: pick([100, 100, 100, 90, 100, 90, 50])(i) },
  ]),
  topSources: [
    {
      maskedIp: "198.51.100.x",
      key: null,
      client: "TOOL",
      requests: 1520,
      peakPerMinute: 180,
      topPath: "/api/v1/notices/{id}",
      firstSeen: "2026-10-23T05:10:00Z",
      lastSeen: "2026-10-23T06:02:00Z",
    },
    {
      maskedIp: "66.249.66.x",
      key: null,
      client: "SEARCH_BOT",
      requests: 820,
      peakPerMinute: 12,
      topPath: "/api/v1/notices",
      firstSeen: "2026-10-20T00:01:00Z",
      lastSeen: "2026-10-26T02:58:00Z",
    },
  ],
  topBotPaths: [
    { path: "/api/v1/notices/{id}", requests: 4100, humanRequests: 2300, botRequests: 1800 },
    { path: "/api/v1/notices", requests: 3900, humanRequests: 3100, botRequests: 800 },
  ],
  statuses: [
    { group: "401", requests: 140 },
    { group: "403", requests: 12 },
    { group: "404", requests: 260 },
    { group: "5xx", requests: 3 },
  ],
  adminAccess: [
    {
      at: "2026-10-26T02:51:00Z",
      method: "POST",
      path: "/api/admin/reviews/{id}/approve",
      status: 200,
      maskedIp: "203.0.113.x",
      client: "HUMAN",
    },
  ],
  loginFailures: [
    {
      at: "2026-10-23T05:20:00Z",
      method: "GET",
      path: "/login/oauth2/code/kakao",
      status: 302,
      maskedIp: "198.51.100.x",
      client: "TOOL",
    },
  ],
};

export const realtimeMock: RealtimeData = {
  connected: true,
  error: null,
  fetchedAt: "2026-10-27T03:00:00Z",
  last30Minutes: 23,
  last5Minutes: 6,
  devices: [
    { name: "mobile", value: 17, users: 17 },
    { name: "desktop", value: 6, users: 6 },
  ],
};

/** 목업 공고 제목 (사용자 화면 /notices/n1 …) */
export const noticeTitlesMock: Record<string, string> = {
  n1: "○○ 행복주택 입주자 모집",
  n2: "○○ 국민임대 예비입주자 모집",
  n3: "○○ 장기전세",
};
