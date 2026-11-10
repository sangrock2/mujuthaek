// 화면용 예시 데이터 (디자인 AdminWebHome · AdminWebReview · AdminWebSources · AdminWebCriteria · AdminWebReports). 실제 값은 API에서 받아요.
import { routes } from "@/lib/routes";

/* 사이드바 숫자 */
/** 사이드바 숫자. null이면 그 숫자를 받지 못한 것(숫자 표시를 숨겨요) */
export type AdminCounts = {
  reviewPending: number | null;
  sourceIssues: number | null;
  newReports: number | null;
  /** 검토 전 채팅 신고가 있는 메시지 수 */
  chatReports: number | null;
  /** 처리 전 중복 의심 사업 수 */
  policyDuplicates: number | null;
};

export const adminCounts: AdminCounts = {
  reviewPending: 12,
  sourceIssues: 2,
  newReports: 5,
  chatReports: 2,
  policyDuplicates: 1,
};

export const adminOperator = "김○○";

/* 개요 */
export type AdminTodoKind = "deadline" | "source" | "report" | "criteria";

export type AdminTodo = { id: string; kind: AdminTodoKind; title: string; desc: string };

export type AdminOverview = {
  asOf: string;
  /** count가 null이면 불러오지 못한 숫자예요 (화면은 「-」) */
  review: { count: number | null; oldest: string };
  collected: { count: number | null; note: string };
  issues: { count: number | null; note: string };
  reports: { count: number | null; note: string };
  todos: AdminTodo[];
  quality: {
    asIs: string;
    edited: string;
    rejected: string;
    medianTime: string;
    fixedByReport: string;
  };
  today: {
    approved: number | null;
    editedApproved: number | null;
    rejected: number | null;
    replied: number | null;
  };
};

export const adminOverview: AdminOverview = {
  asOf: "10월 20일 (화) 14:30",
  review: { count: 12, oldest: "18시간" },
  collected: { count: 148, note: "새 공고·정책 46 · 내용 바뀜 9" },
  issues: { count: 2, note: "실패 1 · 지연 1" },
  reports: { count: 5, note: "같은 공고에 3건 몰림" },
  todos: [
    {
      id: "t1",
      kind: "deadline",
      title: "마감 D-3인데 아직 검수 안 된 정책 2건",
      desc: "청년 월세 지원 · ○○광역시 외 1건 · 사용자에게 아직 안 보여요",
    },
    {
      id: "t2",
      kind: "source",
      title: "GH 청약센터 3회 연속 0건",
      desc: "게시판 구조가 바뀌었을 수 있어요 · 마지막 정상 수집 어제 06:00",
    },
    {
      id: "t3",
      kind: "report",
      title: "같은 공고에 '금액이 틀려요' 제보 3건",
      desc: "○○지구 행복주택 · 보증금",
    },
    {
      id: "t4",
      kind: "criteria",
      title: "2027년 기준중위소득 고시값 입력",
      desc: "입력해 두면 1월 1일 0시에 적용돼요 · 이 값을 쓰는 판정 규칙 23개",
    },
  ],
  quality: {
    asIs: "82%",
    edited: "15%",
    rejected: "3%",
    medianTime: "4시간",
    fixedByReport: "6건",
  },
  today: { approved: 31, editedApproved: 5, rejected: 1, replied: 4 },
};

/* 검수 */
export type ReviewReason = "must" | "low" | "format";
export type SourcePartKind = "ok" | "low" | "plain";

export type ReviewItem = {
  id: string;
  reason: ReviewReason;
  kind: string;
  title: string;
  source: string;
  version: string;
  received: string;
  age: string;
  paras: { head: string; parts: { t: string; kind: SourcePartKind }[] }[];
  fields: {
    label: string;
    value: string;
    conf: number;
    /** 백엔드 칸 상태: HELD(확인 전까지 안 보임)·CHECK(확인 필요)·EMPTY(값 없음). 없으면 문제 없음 */
    status?: "HELD" | "CHECK" | "EMPTY";
    /** 그 칸을 보는 이유 */
    why?: string;
  }[];
  impact: string;
  log: { at: string; who: string; text: string }[];
};

const ok = (t: string) => ({ t, kind: "ok" as const });
const low = (t: string) => ({ t, kind: "low" as const });
const plain = (t: string) => ({ t, kind: "plain" as const });

export const reviewQueue: { total: number; items: ReviewItem[] } = {
  total: 12,
  items: [
    {
      id: "r1",
      reason: "must",
      kind: "광역 정책",
      title: "청년 월세 지원 · ○○광역시",
      source: "정부24",
      version: "원문 버전 2",
      received: "10월 19일 20:12",
      age: "18시간 전",
      paras: [
        {
          head: "[지원 대상]",
          parts: [
            plain("공고일 현재 ○○광역시에 주민등록을 둔 "),
            ok("만 19세 이상 34세 이하"),
            plain(" 무주택 청년으로서, "),
            low("기준중위소득 150% 이하"),
            plain("인 사람"),
          ],
        },
        {
          head: "[지원 내용]",
          parts: [ok("월 최대 20만 원"), plain(", "), ok("최대 12개월"), plain(" 지원")],
        },
        {
          head: "[신청 기간]",
          parts: [ok("10월 1일 ~ 10월 23일"), plain(" (예산 소진 시 조기 마감)")],
        },
      ],
      fields: [
        { label: "나이", value: "만 19~34세", conf: 0.95 },
        { label: "소득 기준", value: "중위소득 150% 이하 (원가구?)", conf: 0.58 },
        { label: "지원 금액", value: "월 20만 원", conf: 0.93 },
        { label: "지원 기간", value: "12개월", conf: 0.91 },
        { label: "신청 마감", value: "10월 23일", conf: 0.88 },
      ],
      impact: "약 1,240명의 판정이 바뀌어요 · 지원 가능 860명 · 확인 필요 380명",
      log: [
        { at: "10월 19일 20:12", who: "시스템", text: "광역 정책이라 검수 대기열에 추가" },
        { at: "10월 19일 20:13", who: "AI", text: "조건 5개 추출 · 소득 기준 신뢰도 낮음" },
      ],
    },
    {
      id: "r2",
      reason: "low",
      kind: "공고",
      title: "○○지구 행복주택 입주자 모집",
      source: "LH 공고 API",
      version: "원문 버전 1",
      received: "10월 20일 06:04",
      age: "8시간 전",
      paras: [
        {
          head: "[신청 자격]",
          parts: [
            plain("무주택 "),
            ok("청년 · 신혼부부 · 고령자"),
            plain(", "),
            low("총자산 2억 5,400만 원 이하"),
            plain(", 자동차 "),
            low("3,708만 원 이하"),
          ],
        },
        {
          head: "[임대 조건]",
          parts: [
            plain("전용 36㎡ 기준 "),
            ok("보증금 2,400만 원"),
            plain(" · "),
            ok("월 18만 원"),
          ],
        },
        { head: "[접수]", parts: [ok("11월 1일 ~ 11월 5일"), plain(" 인터넷 청약")] },
      ],
      fields: [
        { label: "대상", value: "청년 · 신혼부부 · 고령자", conf: 0.92 },
        { label: "자산 기준", value: "2억 5,400만 원 이하", conf: 0.64 },
        { label: "자동차", value: "3,708만 원 이하", conf: 0.66 },
        { label: "보증금", value: "2,400만 원", conf: 0.9 },
        { label: "월 임대료", value: "18만 원", conf: 0.9 },
      ],
      impact: "공고가 열리고 약 3,100명에게 새 공고 알림이 가요",
      log: [
        { at: "10월 20일 06:04", who: "시스템", text: "LH 공고 API에서 새 공고 수집" },
        { at: "10월 20일 06:05", who: "AI", text: "표 안 자산 기준 읽기 신뢰도 낮음" },
      ],
    },
    {
      id: "r3",
      reason: "format",
      kind: "공고",
      title: "○○ 장기전세 입주자 모집",
      source: "SH 공고 게시판",
      version: "원문 버전 1",
      received: "10월 20일 09:31",
      age: "5시간 전",
      paras: [
        {
          head: "[첨부]",
          parts: [plain("공고문이 "), low("스캔 이미지 PDF"), plain("라 글자를 읽지 못했어요")],
        },
        {
          head: "[게시판 본문]",
          parts: [plain("모집 호수 "), ok("120호"), plain(" · 접수 "), ok("11월 10일 ~ 11월 12일")],
        },
      ],
      fields: [
        { label: "모집 호수", value: "120호", conf: 0.86 },
        { label: "접수 기간", value: "11월 10일 ~ 11월 12일", conf: 0.84 },
        { label: "소득 기준", value: "", conf: 0 },
        { label: "전세금", value: "", conf: 0 },
      ],
      impact: "빈 칸이 있어 승인해도 이 공고의 판정은 모두 확인 필요로 보여요",
      log: [{ at: "10월 20일 09:31", who: "시스템", text: "첨부 PDF 글자 인식 실패 · 형식 오류" }],
    },
    {
      id: "r4",
      reason: "low",
      kind: "기초 정책",
      title: "신혼부부 이사비 지원 · ○○구",
      source: "○○구청 게시판",
      version: "원문 버전 1",
      received: "10월 20일 11:02",
      age: "3시간 전",
      paras: [
        {
          head: "[지원 대상]",
          parts: [plain("○○구 전입 "), low("혼인 7년 이내"), plain(" 무주택 신혼부부")],
        },
        { head: "[지원 내용]", parts: [plain("이사비·중개수수료 "), ok("최대 40만 원")] },
      ],
      fields: [
        { label: "대상", value: "혼인 7년 이내 신혼부부", conf: 0.67 },
        { label: "거주 요건", value: "○○구 전입", conf: 0.89 },
        { label: "지원 금액", value: "최대 40만 원", conf: 0.94 },
      ],
      impact: "약 90명의 판정이 바뀌어요 · 지원 가능 70명 · 확인 필요 20명",
      log: [{ at: "10월 20일 11:02", who: "시스템", text: "○○구청 게시판에서 새 정책 수집" }],
    },
  ],
};

/* 수집 현황 */
export type SourceStatus = "ok" | "late" | "fail";
export type SourceRun = { at: string; text: string; tone: "normal" | "fail" | "late" };

export type SourceRow = {
  id: string;
  name: string;
  area: string;
  method: string;
  cycle: string;
  last: string;
  count: number;
  st: SourceStatus;
  issue?: string;
  runs: SourceRun[];
  robots: string;
  parser: string;
  total: string;
};

const okRuns = (n: number): SourceRun[] => [
  { at: "오늘 14:00", text: `${n}건`, tone: "normal" },
  { at: "오늘 06:00", text: "정상", tone: "normal" },
  { at: "어제 22:00", text: "정상", tone: "normal" },
];

const ROBOTS_OK = "10월 1일 확인 · 공고 경로 허용";
const ROBOTS_API = "해당 없음 (API)";
const API = "공공데이터 API";
const BOARD_V3 = "게시판 표 읽기 v3";

export const adminSources: {
  total: number;
  asOf: string;
  summary: { ok: number; late: number; fail: number };
  rows: SourceRow[];
} = {
  total: 11,
  asOf: "10월 20일 14:30",
  summary: { ok: 9, late: 1, fail: 1 },
  rows: [
    {
      id: "gh",
      name: "GH 청약센터",
      area: "주거 · 경기",
      method: "게시판",
      cycle: "하루 3회",
      last: "오늘 14:00",
      count: 0,
      st: "fail",
      issue: "목록 표의 구조가 바뀌었을 수 있어요. 어제 06:00 이후 새 글을 하나도 못 읽었어요.",
      runs: [
        { at: "오늘 14:00", text: "0건 · 표 못 찾음", tone: "fail" },
        { at: "오늘 06:00", text: "0건 · 같은 오류", tone: "fail" },
        { at: "어제 22:00", text: "0건 · 같은 오류", tone: "fail" },
        { at: "어제 06:00", text: "4건", tone: "normal" },
      ],
      robots: ROBOTS_OK,
      parser: BOARD_V3,
      total: "1,284건",
    },
    {
      id: "lh",
      name: "LH 공고 API",
      area: "주거 · 전국",
      method: "API",
      cycle: "하루 3회",
      last: "오늘 14:00",
      count: 12,
      st: "ok",
      runs: okRuns(12),
      robots: ROBOTS_API,
      parser: API,
      total: "8,902건",
    },
    {
      id: "apt",
      name: "청약홈 API",
      area: "주거 · 전국",
      method: "API",
      cycle: "하루 3회",
      last: "오늘 14:00",
      count: 7,
      st: "ok",
      runs: okRuns(7),
      robots: ROBOTS_API,
      parser: API,
      total: "5,117건",
    },
    {
      id: "sh",
      name: "SH 공고 게시판",
      area: "주거 · 서울",
      method: "게시판",
      cycle: "하루 3회",
      last: "오늘 14:00",
      count: 3,
      st: "ok",
      runs: okRuns(3),
      robots: ROBOTS_OK,
      parser: BOARD_V3,
      total: "942건",
    },
    {
      id: "ih",
      name: "iH 공고 게시판",
      area: "주거 · 인천",
      method: "게시판",
      cycle: "하루 3회",
      last: "오늘 14:00",
      count: 1,
      st: "ok",
      runs: okRuns(1),
      robots: ROBOTS_OK,
      parser: BOARD_V3,
      total: "411건",
    },
    {
      id: "gov",
      name: "정부24 · 온통청년",
      area: "정책 · 전국",
      method: "API",
      cycle: "하루 1회",
      last: "어제 03:00",
      count: 21,
      st: "late",
      issue: "오늘 03:00 수집이 응답 시간 초과로 미뤄졌어요. 다음 시도 15:00.",
      runs: [
        { at: "오늘 03:00", text: "시간 초과", tone: "late" },
        { at: "어제 03:00", text: "21건", tone: "normal" },
        { at: "그제 03:00", text: "18건", tone: "normal" },
      ],
      robots: ROBOTS_API,
      parser: API,
      total: "3,560건",
    },
    {
      id: "bok",
      name: "복지로",
      area: "정책 · 전국",
      method: "API",
      cycle: "하루 1회",
      last: "오늘 03:00",
      count: 5,
      st: "ok",
      runs: okRuns(5),
      robots: ROBOTS_API,
      parser: API,
      total: "1,203건",
    },
    {
      id: "local",
      name: "지자체 청년정책 게시판",
      area: "정책 · 시군구 38곳",
      method: "게시판",
      cycle: "하루 1회",
      last: "오늘 04:00",
      count: 9,
      st: "ok",
      runs: okRuns(9),
      robots: "곳마다 확인 · 38곳 허용",
      parser: "게시판 글 읽기 v2",
      total: "2,018건",
    },
    {
      id: "kstart",
      name: "K-Startup 사업공고",
      area: "사업 · 전국",
      method: "API",
      cycle: "하루 1회",
      last: "오늘 05:00",
      count: 6,
      st: "ok",
      runs: okRuns(6),
      robots: ROBOTS_API,
      parser: API,
      total: "1,377건",
    },
    {
      id: "shop",
      name: "LH · SH 상가 입찰",
      area: "사업 · 수도권",
      method: "게시판",
      cycle: "하루 1회",
      last: "오늘 05:00",
      count: 2,
      st: "ok",
      runs: okRuns(2),
      robots: "10월 1일 확인 · 입찰 경로 허용",
      parser: BOARD_V3,
      total: "326건",
    },
    {
      id: "share",
      name: "공유누리",
      area: "사업 · 회의실",
      method: "API",
      cycle: "하루 2회",
      last: "오늘 12:00",
      count: 40,
      st: "ok",
      runs: okRuns(40),
      robots: ROBOTS_API,
      parser: API,
      total: "9,840건",
    },
  ],
};

/* 기준값 */
export type AdminCriteria = {
  incomeBase: number[];
  rulesCount: number;
  rules: { name: string; ratio: string }[];
  history: { title: string; meta: string }[];
  score: { max: number; lastChecked: string; items: { name: string; max: number; rule: string }[] };
  regions: { name: string; scope: string }[];
};

export const adminCriteria: AdminCriteria = {
  incomeBase: [2564238, 4199292, 5359036, 6494738, 7556719, 8555952],
  rulesCount: 23,
  rules: [
    { name: "청년 월세 지원 (국토부)", ratio: "60% · 100%" },
    { name: "서울시 청년 월세 지원", ratio: "150%" },
    { name: "청년도약계좌", ratio: "250%" },
  ],
  history: [
    { title: "2026년 값 적용", meta: "1월 1일 00:00 · 예약 적용 · 김○○" },
    { title: "2026년 값 입력", meta: "2025년 8월 1일 · 김○○ · 고시문 첨부" },
  ],
  score: {
    max: 84,
    lastChecked: "9월 2일",
    items: [
      { name: "무주택 기간", max: 32, rule: "1년 미만 2점 · 1년마다 2점 더해요 · 15년 이상 32점" },
      { name: "부양가족 수", max: 35, rule: "0명 5점 · 1명마다 5점 더해요 · 6명 이상 35점" },
      {
        name: "청약통장 가입 기간",
        max: 17,
        rule: "6개월 미만 1점 · 1년마다 1점 더해요 · 15년 이상 17점",
      },
    ],
  },
  regions: [
    { name: "서울특별시", scope: "전체" },
    { name: "인천광역시", scope: "일부 · 강화군, 옹진군, 경제자유구역 등 제외" },
    {
      name: "경기도",
      scope:
        "의정부, 구리, 남양주(일부), 하남, 고양, 수원, 성남, 안양, 부천, 광명, 과천, 의왕, 군포, 시흥(일부)",
    },
  ],
};

/* 제보 */
export type ReportStatus = "new" | "doing" | "done";

export type ReportItem = {
  id: string;
  st: ReportStatus;
  where: string;
  target: string;
  field: string;
  current: string;
  reported: string;
  source: string;
  summary: string;
  age: string;
  groupCount: number;
  link: string;
  /** 일반 제보(공고·혜택·사업에 묶이지 않음): 볼 화면이 없고 검수로 보낼 수 없어요 */
  general?: boolean;
  notes: { text: string; meta: string }[];
  reply: string;
};

export const adminReports: {
  /** 목록에 없는 이전 처리 완료 건수 */
  doneBefore: number;
  /** 목록에 없는 새 제보 건수 */
  newBefore: number;
  items: ReportItem[];
} = {
  doneBefore: 18,
  newBefore: 2,
  items: [
    {
      id: "p1",
      st: "new",
      where: "공고 상세 · 내 집",
      target: "○○지구 행복주택",
      field: "보증금",
      current: "2,400만 원",
      reported: "2,600만 원",
      source: "공고문 4쪽 · 청년 전용 36㎡ 보증금 2,600만 원",
      summary: "보증금이 공고문과 달라요",
      age: "2시간 전",
      groupCount: 3,
      link: routes.notice("n1"),
      notes: [
        { text: "공고문 4쪽 표에는 2,600만 원으로 나와요", meta: "사용자 · 오늘 12:20" },
        { text: "보증금이 틀린 것 같아요. 정정 공고가 있었어요", meta: "사용자 · 오늘 10:41" },
      ],
      reply:
        "알려주셔서 고마워요. 정정 공고 내용으로 보증금을 2,600만 원으로 고쳤고, 준비할 돈도 다시 계산했어요.",
    },
    {
      id: "p2",
      st: "new",
      where: "혜택 상세 · 내 혜택",
      target: "서울시 청년 월세 지원",
      field: "신청 기한",
      current: "10월 31일까지",
      reported: "10월 24일 마감",
      source: "서울주거포털 공지 · 예산 소진으로 10월 24일 조기 마감",
      summary: "조기 마감됐대요",
      age: "4시간 전",
      groupCount: 1,
      link: routes.benefits,
      notes: [
        {
          text: "예산이 다 떨어져서 24일에 마감한다고 공지가 올라왔어요",
          meta: "사용자 · 오늘 10:05",
        },
      ],
      reply:
        "알려주셔서 고마워요. 신청 기한을 10월 24일로 고치고, 관심 등록한 분들께 마감 알림을 다시 보냈어요.",
    },
    {
      id: "p3",
      st: "new",
      where: "공간 공고 상세 · 사업공간",
      target: "○○창업보육센터 입주기업 모집",
      field: "관리비",
      current: "월 15만 원",
      reported: "월 12만 원",
      source: "공고문 2쪽 · 1인실 월 15만 원 (부가세 포함)",
      summary: "관리비가 더 싸요",
      age: "어제",
      groupCount: 1,
      link: routes.space("s1"),
      notes: [{ text: "센터에 전화해보니 12만 원이래요", meta: "사용자 · 어제 17:30" }],
      reply:
        "알려주셔서 고마워요. 공고문에는 부가세 포함 월 15만 원으로 나와 있어 그대로 두었어요. 센터에서 다르게 안내받으셨다면 공고 원문을 함께 확인해 주세요.",
    },
    {
      id: "p4",
      st: "doing",
      where: "생활권",
      target: "○○ 국민임대 · 직주근접",
      field: "역까지 거리",
      current: "도보 8분",
      reported: "도보 15분",
      source: "지도 경로 다시 계산 중",
      summary: "역까지 더 멀어요",
      age: "2일 전",
      groupCount: 1,
      link: routes.homes,
      notes: [{ text: "단지 정문 기준이면 15분 넘게 걸려요", meta: "사용자 · 10월 18일" }],
      reply: "알려주셔서 고마워요. 단지 정문 기준으로 다시 계산하고 있어요.",
    },
  ],
};
