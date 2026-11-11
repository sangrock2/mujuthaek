// 관리자 「추출 과정 보기」: GET /api/admin/reviews/{jobId}/trace (추출 서비스 trace_view.py 요약을 api가 그대로 넘겨요)
import { useQuery } from "@tanstack/react-query";
import { API_BASE_URL, ApiError, api, authToken, refreshAccessToken } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";

export type TraceToolCall = { name: string | null; args: string | null };
export type TraceToolResult = { name: string | null; result: string | null; failed: boolean };
/** 담당 대화의 한 차례: 모델이 부른 도구들과 결과, 그 차례 뒤 검증 미들웨어가 알려 준 문제 */
export type TraceTurn = {
  calls: TraceToolCall[];
  results: TraceToolResult[];
  text?: string;
  verify?: string;
};

export type TraceAgent = {
  agent: string | null;
  label: string;
  /** 끝내기 전에 멈춘 이유(호출 상한·예산·모델 오류). 끝까지 갔으면 null */
  stopped: string | null;
  finished: boolean;
  /** 담당이 끝낼 때 남긴 요약 */
  summary: string | null;
  /** 섹션별 넣은 항목 수 */
  items: Record<string, number>;
  coverage: Record<string, { status: string; reason: string | null }>;
  missing: number;
  /** 넣지 못한 항목과 이유 */
  rejected: { item: string; reasons: string[] }[];
  tools: Record<string, number>;
  failedResults: number;
  verifyRounds: number;
  turns: TraceTurn[];
  problems?: unknown[];
  resolver?: {
    targets: number | null;
    before: number | null;
    after: number | null;
    adopted: number | boolean | null;
    runs: number | null;
    conversations: {
      targets: number | null;
      after: number | null;
      adopted: boolean | null;
      stopped: string | null;
      turns: TraceTurn[];
    }[];
  };
  tables?: {
    table: string | null;
    rows: string | null;
    groups: string[] | null;
    stopped: string | null;
    turns: TraceTurn[];
  }[];
};

export type TraceAgentCost = {
  agent: string;
  label: string;
  calls: number;
  seconds: number;
  inputTokens: number;
  cachedTokens: number;
  outputTokens: number;
  costUsd: number;
  cacheHits: number;
};

export type ExtractionTrace = {
  jobId: string;
  jobStatus: string;
  rawPostId: string | null;
  modelUsed: string | null;
  costUsd: number;
  /** V2: 섹션 담당 에이전트 · V1: 예전 방식(합계만) */
  engine: "V2" | "V1";
  totalSeconds: number | null;
  workers: { agent: string; label: string }[];
  totals: {
    costUsd: number;
    calls: number;
    inputTokens: number;
    cachedTokens: number;
    outputTokens: number;
  };
  v1Calls: { calls: number; costUsd: number };
  byAgent: TraceAgentCost[];
  /** 끝내기 전에 멈춘 담당(호출 상한·예산·모델 오류)과 응답을 받지 못한 시도(데우기·구조) */
  stopped: { agent: string | null; label: string; reason: string }[];
  agents: TraceAgent[];
  /** 원문 글자에 들어간 PDF 차례대로 (id는 관리자 원문 PDF API의 fileId). 예전 응답엔 없어요 */
  documents?: TraceDocument[];
  /** 근거 id(줄 p3.12 · 표 행 t4-1.r3 · 칸 t4-1.r3.c2 · 둘째 PDF d2.p3.12) → 원문 PDF 위치 */
  refs?: Record<string, TraceRef>;
};

export type TraceDocument = { id: string; name: string; pageCount: number | null };
/** text: 그 id의 원문 글 (PDF에서 찾아 강조, 예전 작업은 null이라 쪽만 열어요) */
export type TraceRef = { documentId: string; page: number; text: string | null };

/** 글 속 근거 id 후보 (추출 서비스 v2/sources.py와 같은 규칙) */
const REF_TOKEN = /[A-Za-z0-9][A-Za-z0-9.-]*/g;

/** 글을 근거 id와 나머지로 나눠요. refs에 있는 id만 근거로 봐요 */
export function splitRefs(text: string, refs: Record<string, TraceRef> | undefined) {
  const parts: { text: string; ref?: string }[] = [];
  if (!refs || Object.keys(refs).length === 0) return [{ text }];
  let last = 0;
  for (const m of text.matchAll(REF_TOKEN)) {
    const ref = m[0].replace(/[.-]+$/, "");
    if (!refs[ref]) continue;
    const at = m.index ?? 0;
    if (at > last) parts.push({ text: text.slice(last, at) });
    parts.push({ text: ref, ref });
    last = at + ref.length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

/** 관리자 원문 PDF 주소 (GET /api/admin/reviews/{jobId}/files/{fileId}). 목업이면 그 파일 ID의 시연용 예시 PDF (public/mock) */
export function tracePdfUrl(jobId: string | null, fileId: string) {
  return USE_MOCKS || !jobId
    ? `/mock/${encodeURIComponent(fileId)}.pdf`
    : `${API_BASE_URL}/api/admin/reviews/${encodeURIComponent(jobId)}/files/${encodeURIComponent(fileId)}`;
}

/** 로그인이 필요한 관리자 원문 PDF를 받아요 (토큰이 끝났으면 한 번 다시 받아서) */
export async function fetchAdminPdf(src: string): Promise<ArrayBuffer> {
  const send = () =>
    fetch(src, {
      headers: {
        ...(authToken.get() && { Authorization: `Bearer ${authToken.get()}` }),
      },
      credentials: "include",
    });
  let res = await send();
  if (res.status === 401 && (await refreshAccessToken())) res = await send();
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
  return res.arrayBuffer();
}

/** 검수 대기열 항목 ID(「n:작업 ID」) → 작업 ID. 공고가 아니면(혜택 「b:…」) null */
export function traceJobOf(reviewItemId: string): string | null {
  return reviewItemId.startsWith("n:") ? reviewItemId.slice(2) : null;
}

export function useExtractionTrace(jobId: string | null) {
  return useQuery({
    queryKey: ["admin", "extractionTrace", USE_MOCKS ? "mock" : "live", jobId],
    queryFn: () =>
      USE_MOCKS
        ? Promise.resolve(mockTrace)
        : api.get<ExtractionTrace>(`/api/admin/reviews/${jobId}/trace`),
    enabled: USE_MOCKS || Boolean(jobId),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/** 목업에서 「추출 과정 보기」를 여는 검수 대기열 항목 (○○지구 행복주택 · 공고 n1과 같은 공고) */
export const MOCK_TRACE_REVIEW_ID = "r2";

const DEMO_FILE = "notice-n1";

/**
 * 목업: 실제 V2 기록과 같은 모양의 예. 검수 대기열 r2(○○지구 행복주택)의 추출 기록이고, 근거 id(refs)의 글은 시연용 예시 PDF
 * (public/mock/notice-n1.pdf) 3쪽에 그대로 있어서 누르면 그 문장을 강조해요. 자산·자동차 표 칸은 두 번 읽은 값이 달라 확인 필요로 남겨,
 * 공고 화면(n1)에 「원문과 다시 확인하는 중」으로 보여요
 */
export const mockTrace: ExtractionTrace = {
  jobId: "demo-job-n1",
  jobStatus: "PARTIAL",
  rawPostId: null,
  modelUsed: null,
  costUsd: 0.0912,
  engine: "V2",
  totalSeconds: 214.6,
  workers: [
    { agent: "structure", label: "구조 (공고·위치·공급)" },
    { agent: "eligibility", label: "자격 담당" },
    { agent: "schedules", label: "일정 담당" },
    { agent: "selection", label: "선정 담당" },
    { agent: "documents", label: "서류 담당" },
  ],
  totals: {
    costUsd: 0.0912,
    calls: 19,
    inputTokens: 1952000,
    cachedTokens: 1676000,
    outputTokens: 23080,
  },
  v1Calls: { calls: 2, costUsd: 0.0074 },
  byAgent: [
    agentCost("prime", "캐시 데우기", 1, 4.9, 106000, 0, 80, 0.0133, 0),
    agentCost("structure", "구조 (공고·위치·공급)", 1, 21.3, 118000, 104000, 1900, 0.0081, 1),
    agentCost("eligibility", "자격 담당", 6, 96.4, 690000, 640000, 9800, 0.0285, 6),
    agentCost("schedules", "일정 담당", 2, 28.7, 228000, 210000, 2300, 0.0064, 2),
    agentCost("selection", "선정 담당", 2, 22.1, 224000, 208000, 1500, 0.0046, 2),
    agentCost("documents", "서류 담당", 3, 47.5, 345000, 318000, 4100, 0.0101, 3),
    agentCost("resolver", "해결 담당", 2, 39.2, 241000, 196000, 3400, 0.0128, 2),
  ],
  stopped: [],
  documents: [
    { id: DEMO_FILE, name: "○○지구 행복주택 입주자 모집 공고(시연용 예시).pdf", pageCount: 8 },
  ],
  refs: {
    "p3.2": demoRef(3, "청년: 공고일 현재 만 19세 이상 39세 이하인 미혼 무주택자"),
    "p3.3": demoRef(3, "신혼부부: 혼인 기간이 7년 이내인 무주택세대구성원"),
    "p3.4": demoRef(
      3,
      "소득: 세대의 월평균 소득이 전년도 도시근로자 가구원수별 월평균 소득의 100% 이하 (1인 가구는 120% 이하)",
    ),
    "p3.5": demoRef(3, "공고일 현재 세대구성원 전원이 무주택이어야 합니다."),
    "t3-1.r1.c2": demoRef(3, "2억 5,100만 원 이하"),
    "t3-1.r2.c2": demoRef(3, "4,542만 원 이하"),
  },
  agents: [
    {
      agent: "eligibility",
      label: "자격 담당",
      stopped: null,
      finished: true,
      summary:
        "나이·혼인·무주택·소득 기준을 넣었어요. 자산·자동차 기준은 표 1을 두 번 읽은 값이 서로 달라 확인 필요로 남겼어요.",
      items: { eligibility: 6 },
      coverage: { eligibility: { status: "PARTIAL", reason: "자산·자동차 표 칸 확인 필요" } },
      missing: 0,
      rejected: [],
      tools: { add_eligibility: 2, update_item: 1, finish: 1 },
      failedResults: 1,
      verifyRounds: 2,
      resolver: {
        targets: 2,
        before: 2,
        after: 2,
        adopted: 0,
        runs: 1,
        conversations: [{ targets: 2, after: 2, adopted: false, stopped: null, turns: [] }],
      },
      turns: [
        {
          calls: [
            {
              name: "add_eligibility",
              args: '{"items": [{"id": "youth-age", "category": "AGE", "evidence": ["p3.2"]}, {"id": "newlywed", "category": "HOUSEHOLD", "evidence": ["p3.3"]}, {"id": "income", "category": "INCOME", "evidence": ["p3.4"]}, {"id": "homeless", "category": "HOME_OWNERSHIP", "evidence": ["p3.5"]}]}',
            },
          ],
          results: [
            {
              name: "add_eligibility",
              result:
                '{"added": ["newlywed", "income", "homeless"], "failed": [{"id": "youth-age", "errors": ["/rule: 칸이 필요합니다"]}]}',
              failed: true,
            },
          ],
          verify:
            "# 검증 결과\n## 고칠 것 1개\n- youth-age: 조건식(rule)이 없어요. 근거 p3.2의 나이 범위를 rule에 넣어 주세요.",
        },
        {
          calls: [
            {
              name: "update_item",
              args: '{"item": "youth-age", "patch": {"rule": {"min": 19, "max": 39}}}',
            },
            {
              name: "add_eligibility",
              args: '{"items": [{"id": "assets", "category": "ASSETS", "evidence": ["t3-1.r1.c2"]}, {"id": "car", "category": "CAR_ASSETS", "evidence": ["t3-1.r2.c2"]}]}',
            },
          ],
          results: [
            { name: "update_item", result: '{"ok": true}', failed: false },
            { name: "add_eligibility", result: '{"added": ["assets", "car"]}', failed: false },
          ],
          text: "나이 조건식을 고치고, 표 1의 자산·자동차 기준을 넣었어요.",
          verify:
            "# 검증 결과\n## 확인할 것 2개\n- assets: 표 칸 t3-1.r1.c2를 두 번 읽은 금액이 서로 달라요 → 확인 필요로 보류\n- car: 표 칸 t3-1.r2.c2를 두 번 읽은 금액이 서로 달라요 → 확인 필요로 보류",
        },
        {
          calls: [{ name: "finish", args: '{"summary": "자산·자동차 기준은 확인 필요로 남겨요"}' }],
          results: [{ name: "finish", result: '{"ok": true}', failed: false }],
          text: "확인할 것은 해결 담당이 다시 봐도 남아서, 사람 검수로 넘기고 끝낼게요.",
        },
      ],
    },
  ],
};

function agentCost(
  agent: string,
  label: string,
  calls: number,
  seconds: number,
  inputTokens: number,
  cachedTokens: number,
  outputTokens: number,
  costUsd: number,
  cacheHits: number,
): TraceAgentCost {
  return {
    agent,
    label,
    calls,
    seconds,
    inputTokens,
    cachedTokens,
    outputTokens,
    costUsd,
    cacheHits,
  };
}

function demoRef(page: number, text: string): TraceRef {
  return { documentId: DEMO_FILE, page, text };
}
