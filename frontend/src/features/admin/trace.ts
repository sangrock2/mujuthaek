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

/** 관리자 원문 PDF 주소 (GET /api/admin/reviews/{jobId}/files/{fileId}). 목업이면 예시 PDF */
export function tracePdfUrl(jobId: string | null, fileId: string) {
  return USE_MOCKS || !jobId
    ? "/mock/notice-n7.pdf"
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

/** 목업: 실제 V2 기록과 같은 모양의 작은 예 */
export const mockTrace: ExtractionTrace = {
  jobId: "mock-job",
  jobStatus: "PARTIAL",
  rawPostId: null,
  modelUsed: "gpt-6-luna",
  costUsd: 0.0214,
  engine: "V2",
  totalSeconds: 182.4,
  workers: [
    { agent: "structure", label: "구조 (공고·위치·공급)" },
    { agent: "eligibility", label: "자격 담당" },
  ],
  totals: {
    costUsd: 0.0214,
    calls: 6,
    inputTokens: 512000,
    cachedTokens: 400000,
    outputTokens: 5400,
  },
  v1Calls: { calls: 1, costUsd: 0.0012 },
  byAgent: [
    {
      agent: "prime",
      label: "캐시 데우기",
      calls: 1,
      seconds: 4.9,
      inputTokens: 106000,
      cachedTokens: 0,
      outputTokens: 80,
      costUsd: 0.0133,
      cacheHits: 0,
    },
    {
      agent: "eligibility",
      label: "자격 담당",
      calls: 4,
      seconds: 61.2,
      inputTokens: 405000,
      cachedTokens: 400000,
      outputTokens: 5320,
      costUsd: 0.0069,
      cacheHits: 0,
    },
  ],
  stopped: [],
  documents: [{ id: "file-1", name: "공고문.pdf", pageCount: 8 }],
  refs: {
    "p3.2": { documentId: "file-1", page: 3, text: null },
    "t3-1.r1.c2": { documentId: "file-1", page: 3, text: null },
  },
  agents: [
    {
      agent: "eligibility",
      label: "자격 담당",
      stopped: null,
      finished: true,
      summary:
        "나이·무주택·소득·자산 기준과 우선순위 예외를 넣었어요. 자동차 기준은 원문에 없어 넣지 않았어요.",
      items: { eligibility: 12 },
      coverage: { eligibility: { status: "EXTRACTED", reason: null } },
      missing: 0,
      rejected: [],
      tools: { add_eligibility: 2, update_item: 3, finish: 1 },
      failedResults: 1,
      verifyRounds: 2,
      turns: [
        {
          calls: [
            {
              name: "add_eligibility",
              args: '{"items": [{"id": "age", "category": "AGE", "evidence": ["p3.2", "t3-1.r1.c2"]}]}',
            },
          ],
          results: [
            {
              name: "add_eligibility",
              result: '{"failed": [{"id": "age", "errors": ["/rule: 칸이 필요합니다"]}]}',
              failed: true,
            },
          ],
          verify: "# 검증 결과\n## 고칠 것 1개\n- /eligibility/0: 조건식(rule)이 없어요.",
        },
        {
          calls: [
            { name: "update_item", args: '{"item": "age", "patch": {"rule": {"min": 19}}}' },
            { name: "finish", args: '{"summary": "…"}' },
          ],
          results: [
            { name: "update_item", result: '{"ok": true}', failed: false },
            { name: "finish", result: '{"ok": true}', failed: false },
          ],
          text: "나이 조건식을 고쳤어요.",
        },
      ],
    },
  ],
};
