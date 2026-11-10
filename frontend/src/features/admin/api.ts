/**
 * 관리자 화면을 백엔드 관리자 API(mujuthaek-be services/api, /api/admin/**)에 연결하는 어댑터.
 * 백엔드 응답을 화면이 쓰는 타입(@/mocks/admin)으로 바꿔요. NEXT_PUBLIC_USE_MOCKS=false일 때만 써요.
 * 관리자 API는 ADMIN 로그인이 필요해요(토큰은 공통 API 클라이언트가 붙여요).
 */
import { api } from "@/lib/api/client";
import { routes } from "@/lib/routes";
import type { BotTrafficData, RealtimeData, TrafficData } from "@/mocks/admin-traffic";
import { PERMISSION_INFO, type AdminPermission } from "@/features/admin/permissions";
import type {
  AdminChange,
  AdminUser,
  AdminUserFilter,
  AdminUserName,
  AdminUsersPage,
} from "@/mocks/admin-users";
import type { ActivityData, ActivityItem } from "@/mocks/admin-activity";
import type { NotificationStats } from "@/mocks/admin-notifications";
import type { DuplicateList, DuplicateStatus } from "@/mocks/admin-duplicates";
import type {
  ChatReport,
  ChatReportGroup,
  ChatReviewAction,
  ChatReviewStatus,
} from "@/mocks/admin-chat";
import type {
  AdminCriteria,
  AdminCounts,
  AdminOverview,
  AdminTodo,
  ReportItem,
  ReportStatus,
  ReviewItem,
  ReviewReason,
  SourcePartKind,
  SourceRow,
  SourceRun,
  SourceStatus,
} from "@/mocks/admin";

// ---------- 공통 ----------
const KST = "Asia/Seoul";

function when(iso?: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", {
    timeZone: KST,
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ago(iso?: string | null) {
  if (!iso) return "-";
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (min < 60) return `${min}분 전`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}시간 전`;
  return `${Math.round(h / 24)}일 전`;
}

function span(iso?: string | null) {
  if (!iso) return "-";
  const h = Math.round((Date.now() - new Date(iso).getTime()) / 3600000);
  return h < 24 ? `${h}시간` : `${Math.round(h / 24)}일`;
}

// ---------- 검수 (공고 + 혜택 정책) ----------
type NoticeReviewDetail = {
  id: string;
  reason: string;
  title: string;
  field: string;
  provider: string | null;
  sourceCode: string;
  rawVersion: number;
  receivedAt: string;
  detailUrl: string | null;
  issues: { code: string; target: string | null }[];
  fields: {
    path: string;
    section: string;
    label: string;
    status: string;
    value: unknown;
    display: string | null;
    editable: boolean;
    reasons: string[];
    codes?: string[];
    sourceIds: string[];
  }[];
  sources: { id: string; page: number | null; quote: string }[];
  impact: string | null;
  log: { at: string; who: string; text: string }[];
};
type BenefitCondition = {
  type: string;
  value: unknown;
  group: number;
  known: boolean;
  origin: string;
  rawText: string;
  evidence: string;
  confidence: number;
};
const BENEFIT_SOURCE: Record<string, string> = {
  youth: "온통청년",
  gov24: "정부24",
  bokjiro_central: "복지로(중앙부처)",
  bokjiro_local: "복지로(지자체)",
};
type BenefitReviewDetail = {
  id: string;
  /** 목록에서 붙여요(상세 응답에는 없음) */
  sourceCode?: string | null;
  rawVersion: number;
  status: string;
  reasons: string[];
  queuedAt: string;
  decidedAt: string | null;
  decidedBy: string | null;
  note: string | null;
  result: {
    summary: string | null;
    howToApply: string | null;
    contact: string | null;
    relevant: boolean;
    relevanceReason: string;
    source: { title: string; agency: string | null; detailUrl: string | null };
    supports: { kind: string; amountMax: number | null; ratePct: number | null; rawText: string }[];
    conditions: BenefitCondition[];
    quality: { confidence: number };
  };
  source: { title: string | null; text: string | null; detailUrl: string | null };
};

/** 화면의 칸 이름 → 백엔드 칸별 수정 경로. 승인할 때 고친 칸을 edits로 바꿔요. */
export type FieldMeta = { path: string; json: boolean; editable: boolean };
export type ReviewMeta = {
  kind: "notice" | "benefit";
  id: string;
  fields: Record<string, FieldMeta>;
  detailUrl: string | null;
};
export const reviewMeta = new Map<string, ReviewMeta>();

const REASON: Record<string, ReviewReason> = { MUST: "must", CHECK: "low", FORMAT: "format" };
const TYPE_KO: Record<string, string> = {
  AGE: "나이",
  RESIDENCE: "거주",
  INCOME_AMOUNT: "소득",
  INCOME_MEDIAN_PCT: "중위소득",
  ASSET_AMOUNT: "자산",
  HOMELESS: "무주택",
  LEASE: "임대 조건",
  MARITAL: "혼인",
  EDUCATION: "학력",
  EMPLOYMENT: "취업",
  OCCUPATION: "직업",
  WORKPLACE: "직장",
  PREGNANCY: "임신·출산",
  OTHER: "기타",
  EXCLUSIVE: "중복 불가",
  PRIORITY: "우선순위",
};

// 혜택 지원 종류 코드 → 화면 말 (policy.extracted supports[].kind)
const SUPPORT_KO: Record<string, string> = {
  RENT: "월세·임대료",
  DEPOSIT_LOAN: "전월세 보증금 대출",
  PURCHASE_LOAN: "주택 구입 대출",
  HOUSING_SUPPLY: "집 제공",
  MOVE_IN_GRANT: "전입·정착 지원금",
  CASH: "현금 지원",
  OTHER: "기타 지원",
};

// 수집 회차 상태 → 화면 말
const RUN_KO: Record<string, string> = {
  SUCCESS: "성공",
  FAILED: "실패",
  RUNNING: "수집 중",
  PARTIAL: "일부 실패",
};

// 검수 이유 코드 → 사람이 읽는 말 (백엔드 이슈 코드, 혜택 reviewReasons)
const ISSUE_KO: Record<string, string> = {
  PDF_MISSING: "첨부 공고문(PDF)이 없어 게시글만 읽었어요",
  PDF_TEXT_UNREADABLE: "PDF 글자를 읽지 못했어요(스캔 이미지 등)",
  SOURCE_IN_IMAGE_SUSPECTED: "내용이 이미지 안에 있는 것 같아요",
  AI_OUTPUT_ITEM_DROPPED: "AI 결과 일부가 형식이 맞지 않아 빠졌어요",
  AI_OUTPUT_INVALID: "AI 결과 형식이 잘못됐어요",
  VALUE_NOT_IN_QUOTE: "값이 근거 문장에서 확인되지 않아요",
  COVERAGE_PARTIAL_REPORTED: "AI가 일부만 읽었다고 알렸어요",
  CRITERION_NOT_STRUCTURED: "조건을 값으로 바꾸지 못해 글로만 남았어요",
  RELATION_UNRESOLVED: "정정·후속 공고의 원래 공고를 찾지 못했어요",
  LOW_CONFIDENCE:
    "확실하지 않은 값이 있어요(기준이 원문에 없거나, 같은 문장에 다른 금액이 있는 등)",
  RULE_AI_CONFLICT: "출처 항목 값과 원문 글에서 읽은 값이 달라요",
  EVIDENCE_NOT_FOUND: "AI가 든 근거 문장이 원문에 없어요",
  TEXT_TRUNCATED: "원문이 길어 일부만 읽었어요",
  NO_DOCUMENT: "첨부 문서 없이 정책 항목만으로 읽었어요(참고)",
  REPORTED: "다시 열린 검수예요(회원 제보나 원문 대조, 아래 기록의 메모 참고)",
  CONTRACT_EXCEPTIONS_NOT_REVIEWED: "예외 조건을 AI가 다 살폈는지 확인되지 않았어요",
  CONTRACT_INCOMPLETE_EXTRACTION: "추출이 끝까지 되지 않았어요",
  CONTRACT_UNRESOLVED_MISSING_FIELD: "빠진 칸이 아직 채워지지 않았어요",
  COUNT_KIND_SUSPECTED: "호수를 표의 다른 열에서 읽은 것 같아요",
  COUNT_MERGED_AMBIGUOUS: "합쳐진 호수를 나누기 어려워요",
  COVERAGE_FAILED: "읽어야 할 부분을 읽지 못했어요",
  COVERAGE_PARTIAL: "일부만 읽었어요",
  ELIGIBILITY_OMISSION_SUSPECTED: "원문에 있는 자격 조건이 빠진 것 같아요",
  EVIDENCE_AMBIGUOUS: "근거 문장이 여러 곳에 있어 어느 것인지 애매해요",
  EVIDENCE_QUOTE_NOT_FOUND: "근거 문장을 원문에서 찾지 못했어요",
  EVIDENCE_SCATTERED: "근거 낱말이 원문에 흩어져 있어요",
  EXCEPTION_SUSPECTED: "예외 조건이 있는 것 같아요",
  ITEM_DROPPED_NO_EVIDENCE: "근거를 찾지 못한 항목을 뺐어요",
  ITEM_QUARANTINED: "형식 오류로 항목을 뺐어요",
  MISSING_FIELD_HAS_VALUE: "AI가 없다고 한 칸에 값이 있어요",
  ORIGINAL_TEXT_NOT_FOUND: "원문 그대로여야 하는 문장이 원문에 없어요",
  PRICE_PLAN_MIXED: "보증금·임대료 전환안 금액이 섞였을 수 있어요",
  PRICE_VALUES_UNUSED: "원문 금액 일부가 쓰이지 않았어요",
  TIER_CONDITION_MISSING: "가구원 수·자녀 수별 기준이 구분되지 않았어요",
  VALUE_POSITION_SUSPECTED: "표의 다른 칸 값을 읽은 것 같아요",
  AI_OUTPUT_VALUE_CHANGED: "AI가 준 값을 프로그램이 바꾸거나 비웠어요(원문 확인 필요)",
  DUPLICATE_SUSPECTED:
    "같은 출처에 같은 정책이 따로 또 있어요(중복 의심 · 둘 중 하나를 반려할지 확인)",
  // 2026-10-26 원문 대조 뒤 더한 코드들(번역이 없으면 영어 코드가 그대로 보였음)
  AI_TEXT_FOREIGN_SCRIPT: "AI가 쓴 문장에 원문에 없는 외국 문자(일본어·한자)가 섞였어요",
  AI_OUTPUT_FIELD_CLEARED: "형식이 맞지 않는 칸을 비웠어요",
  AI_OUTPUT_ITEM_COERCED: "AI가 준 항목의 칸을 형식에 맞게 바꿨어요",
  AI_OUTPUT_ID_RENAMED: "겹친 항목 번호를 바꿨어요(참고)",
  DETAIL_UNVERIFIED_CLEARED: "근거에서 확인하지 못한 세부 칸(시각·장소·부수 등)을 비웠어요",
  INCOMPLETE_EXTRACTION: "추출이 끝까지 되지 않았어요",
  UNRESOLVED_MISSING_FIELD: "빠진 칸이 아직 채워지지 않았어요",
  EXCEPTIONS_NOT_REVIEWED: "예외 조건을 AI가 다 살폈는지 확인되지 않았어요",
  API_MISMATCH: "공공 API 값과 원문에서 읽은 값이 달라요",
  OPERATOR_MISMATCH: "이상·이하 같은 비교 방향이 원문과 달라 보여요",
  EVIDENCE_QUOTE_TOO_SHORT: "근거 문장이 너무 짧아 어디인지 확실하지 않아요",
  EVIDENCE_FROM_IMAGE: "근거가 그림 속 글자(AI가 옮겨 씀)예요",
  IMAGE_TRANSCRIBED_VALUES: "그림 속 글자를 옮긴 값이에요(참고)",
  ITEM_WITHOUT_EVIDENCE: "근거 문장이 없는 항목이에요",
  CLAIM_UNSUPPORTED: "설명 문장이 근거 문장과 맞지 않아요",
  COUNT_TOTAL_SUSPECTED: "합계를 유형별 호수로 읽은 것 같아요",
  SUPPLY_PRICE_MISSING: "주택형에 금액이 없어요",
  SUPPLY_PRICE_UNATTACHED: "금액이 어느 주택형인지 붙지 않았어요",
  PRICE_SCOPE_UNCERTAIN: "금액이 어느 대상·주택형 것인지 확실하지 않아요",
  PRICE_UNIT_MISMATCH: "금액 단위가 원문과 달라 보여요",
  PRICE_ROWS_UNUSED: "원문 금액 표 일부가 쓰이지 않았어요",
  RENT_EXCEEDS_DEPOSIT: "월 임대료가 보증금보다 커요(뒤바뀜 의심)",
  CONVERSION_DIRECTION_UNCERTAIN: "보증금 전환 방향(올림·내림)이 확실하지 않아요",
  CONVERSION_DIRECTION_CORRECTED: "보증금 전환 방향을 숫자에 맞게 고쳤어요(참고)",
  DOCUMENT_OMISSION_SUSPECTED: "원문 서류 표에 있는 서류가 빠진 것 같아요",
  DOCUMENT_GROUP_CONFLICT: "서류가 공통·해당자 중 어디인지 엇갈려요",
  LIST_OMISSION_SUSPECTED: "원문 목록 일부가 빠진 것 같아요",
  SECTION_OMISSION_SUSPECTED: "원문에 있는 내용 묶음이 통째로 빠진 것 같아요",
  SCORING_OMISSION_SUSPECTED: "배점표 일부가 빠진 것 같아요",
  SCHEDULE_ORDER_SUSPECTED: "일정 순서가 이상해요",
  SCOPE_LOCATION_CONFLICT: "적용 단지가 서로 엇갈려요",
  SUPPLY_TYPE_AMBIGUOUS: "공급 유형이 확실하지 않아요",
  RELATION_INCONSISTENT: "정정·후속 공고 관계가 맞지 않아요",
  RENEWAL_CRITERION_IN_ELIGIBILITY: "재계약 기준이 신청 자격에 섞였어요",
  NOT_A_NOTICE_SUSPECTED: "모집 공고가 아닌 안내 글 같아요",
  UNITS_DISAGREE: "주택 목록과 공고문 값이 달라요",
  VALUE_OUT_OF_RANGE: "값이 있을 수 없는 범위예요",
  MISSING_FIELD_NEEDS_REVIEW: "빈칸 이유를 확인해야 해요",
  PDF_PAGES_UNREADABLE: "PDF 일부 쪽을 읽지 못했어요",
  PDF_TOO_LONG: "PDF가 너무 길어 일부만 읽었어요",
  SOURCE_TEXT_EMPTY: "원문 글자가 비어 있어요",
  ATTACHMENT_TYPE_UNSUPPORTED: "공고문이 읽을 수 없는 형식(HWP 등)이에요",
  ATTACHMENT_UNAVAILABLE: "첨부 파일을 받지 못했어요",
  NOTICE_DOC_NOT_PDF: "공고문이 PDF가 아니에요(HWP 등)",
};
const TARGET_KO: Record<string, string> = {
  documents: "첨부 문서",
  supplyGroups: "공급 주택",
  eligibility: "자격 조건",
  schedules: "일정",
  locations: "위치",
  requiredDocuments: "제출 서류",
  announcedOn: "공고일",
  units: "주택 목록",
};
function issueText(code: string, target: string | null) {
  const base = code.replace(/:$/, "");
  // 계약 검사 코드는 「CONTRACT_」를 떼고도 찾아요. 모르는 코드는 영어 코드 대신 일반 문구로(내부 용어가 보이지 않게)
  const text =
    ISSUE_KO[base] ??
    ISSUE_KO[base.replace(/^(CONTRACT_|COVERAGE_)/, "")] ??
    (base.startsWith("CONTRACT_") || base.startsWith("SCHEMA")
      ? "형식·완료 조건 검사에서 걸렸어요"
      : "자동 검사에서 확인이 필요하다고 표시했어요");
  if (!target) return text;
  if (!target.startsWith("/")) return `${text} · ${target}`;
  const key = target
    .split("/")
    .filter(Boolean)
    .reverse()
    .find((k) => TARGET_KO[k]);
  return key ? `${text} · ${TARGET_KO[key]}` : text;
}

/**
 * 검수 칸 이름에서 내부 용어를 사람이 읽는 말로 바꿔요: 같은 말 반복(「자격 조건 · 자격 조건」), 묶음 ID(sg-t3-5-r4),
 * JSON 위치(prices.30, rule.expression.children.1.value)가 그대로 보였어요
 */
function fieldLabel(section: string, label: string) {
  const parts = [section, ...label.split(" · ")].map((p) => p.trim()).filter(Boolean);
  const out: string[] = [];
  for (const p of parts) {
    let t = p;
    if (/^sg-[\w-]+$/.test(t)) t = "주택형 묶음";
    else if (/^prices(\.\d+)?$/.test(t))
      t = t.includes(".") ? `금액 ${Number(t.split(".")[1]) + 1}번째` : "금액";
    else if (/^counts(\.\d+)?$/.test(t)) t = "호수";
    else if (/^exceptions\./.test(t)) t = "예외 조건의 값";
    else if (/(^|\.)(rule|expression|effectExpression|children|value)(\.|$)/.test(t))
      t = "조건의 값";
    if (out[out.length - 1] !== t) out.push(t);
  }
  return out.join(" · ");
}

function noticeItem(d: NoticeReviewDetail): ReviewItem {
  const held = new Set(d.fields.filter((f) => f.status === "HELD").flatMap((f) => f.sourceIds));
  const byPage = new Map<string, { t: string; kind: SourcePartKind }[]>();
  for (const s of d.sources) {
    const head = s.page ? `${s.page}쪽` : "원문";
    byPage.set(head, [
      ...(byPage.get(head) ?? []),
      { t: s.quote + " ", kind: held.has(s.id) ? "low" : "ok" },
    ]);
  }
  const fields: Record<string, FieldMeta> = {};
  // 칸 이름이 길어 잘리면 서로 같아질 수 있어요. 이름은 화면 key이자 수정값을 찾는 열쇠라 겹치면 번호를 붙여요
  const seen = new Map<string, number>();
  const rows = d.fields.map((f) => {
    const base = fieldLabel(f.section, f.label);
    const n = (seen.get(base) ?? 0) + 1;
    seen.set(base, n);
    const label = n > 1 ? `${base} (${n})` : base;
    fields[label] = { path: f.path, json: typeof f.value !== "string", editable: f.editable };
    // 백엔드는 신뢰도 숫자 대신 「확인 필요 + 이유」예요. 화면이 숫자를 쓰니 보류(HELD)는 낮게, 확인(CHECK)은 중간으로 바꿔 보여 줘요
    return {
      label,
      value: f.display ?? (typeof f.value === "string" ? f.value : JSON.stringify(f.value)),
      conf: f.status === "HELD" ? 0.3 : 0.6,
      status: (f.status === "HELD" ? "HELD" : "CHECK") as "HELD" | "CHECK",
      why: [...new Set((f.codes ?? []).map((c) => issueText(c, null)))].join(" / ") || undefined,
    };
  });
  reviewMeta.set(`n:${d.id}`, { kind: "notice", id: d.id, fields, detailUrl: d.detailUrl ?? null });
  // 검수에 온 이유를 원문 칸 맨 위에 보여 줘요. 확인할 칸·근거가 없는 건(PDF 없음 등)도 무엇을 볼지 알 수 있게
  const why = [...new Set(d.issues.map((i) => issueText(i.code, i.target)))];
  const reasonPara = {
    head: "검수 이유",
    parts: [
      { t: why.length ? why.join(" / ") : "이유 코드가 없어요", kind: "low" as SourcePartKind },
    ],
  };
  const emptyPara = byPage.size
    ? []
    : [
        {
          head: "원문 근거",
          parts: [
            {
              t: "뽑힌 근거 문장이 없어요. 「원문 사이트」에서 공고를 직접 확인해 주세요.",
              kind: "plain" as SourcePartKind,
            },
          ],
        },
      ];
  return {
    id: `n:${d.id}`,
    reason: REASON[d.reason] ?? "low",
    kind: `${d.field === "HOUSING" ? "주거 공고" : "사업공간 공고"}${d.provider ? " · " + d.provider : ""}`,
    title: d.title,
    source: (d.provider ?? d.sourceCode).toUpperCase(),
    version: `v${d.rawVersion}`,
    received: when(d.receivedAt),
    age: ago(d.receivedAt),
    paras: [
      reasonPara,
      ...emptyPara,
      ...[...byPage.entries()].map(([head, parts]) => ({ head, parts })),
    ],
    fields: rows,
    impact: d.impact ?? "검수한 값이 서비스에 반영돼요",
    log: d.log.map((l) => ({ at: when(l.at), who: l.who, text: l.text })),
  };
}

function benefitItem(d: BenefitReviewDetail): ReviewItem {
  const r = d.result;
  const evidence = new Map(r.conditions.map((c) => [c.evidence.replace(/\s+/g, ""), c.known]));
  // 「항목: 값」 줄은 새 문단, 그 밖의 줄은 앞 문단에 이어 붙여요(문단 머리말이 화면의 key라 겹치지 않게)
  const paras: { head: string; parts: { t: string; kind: SourcePartKind }[] }[] = [];
  const heads = new Map<string, number>();
  for (const line of (d.source.text ?? "")
    .split("\n")
    .filter((l) => l.trim())
    .slice(0, 80)) {
    const m = /^([^:]{1,30}):\s*(.*)$/.exec(line.trim());
    const body = m ? m[2] : line.trim();
    const key = line.replace(/\s+/g, "");
    const hit = [...evidence.entries()].find(([e]) => e && key.includes(e));
    const part = {
      t: body + " ",
      kind: (hit ? (hit[1] ? "ok" : "low") : "plain") as SourcePartKind,
    };
    if (m || !paras.length) {
      const base = m ? m[1].trim() : "원문";
      const n = (heads.get(base) ?? 0) + 1;
      heads.set(base, n);
      paras.push({ head: n > 1 ? `${base} (${n})` : base, parts: [part] });
    } else {
      paras[paras.length - 1].parts.push(part);
    }
  }
  const fields: Record<string, FieldMeta> = {
    요약: { path: "/summary", json: false, editable: true },
    "신청 방법": { path: "/howToApply", json: false, editable: true },
    문의처: { path: "/contact", json: false, editable: true },
  };
  const rows = [
    { label: "요약", value: r.summary ?? "", conf: r.quality.confidence },
    { label: "신청 방법", value: r.howToApply ?? "", conf: r.quality.confidence },
    { label: "문의처", value: r.contact ?? "", conf: r.quality.confidence },
    ...r.supports.map((s, i) => {
      const label = `지원 ${i + 1} · ${SUPPORT_KO[s.kind] ?? "기타 지원"}`;
      fields[label] = { path: `/supports/${i}/amountMax`, json: true, editable: true };
      return {
        label,
        value: s.amountMax == null ? "" : String(s.amountMax),
        conf: s.amountMax == null ? 0 : r.quality.confidence,
        status: s.amountMax == null ? ("EMPTY" as const) : undefined,
      };
    }),
    ...r.conditions.map((c, i) => {
      const label = `${TYPE_KO[c.type] ?? c.type} (묶음 ${c.group}) · ${i + 1}`;
      fields[label] = {
        path: `/conditions/${i}/value`,
        json: true,
        editable: !["OTHER", "EXCLUSIVE", "PRIORITY"].includes(c.type),
      };
      return {
        label,
        value: c.known ? JSON.stringify(c.value) : c.rawText,
        conf: c.known ? c.confidence : 0,
        status: c.known ? undefined : ("EMPTY" as const),
        why: c.known ? undefined : "판정에 쓰는 값이 없어 글로만 보여요",
      };
    }),
  ];
  reviewMeta.set(`b:${d.id}`, { kind: "benefit", id: d.id, fields, detailUrl: r.source.detailUrl });
  return {
    id: `b:${d.id}`,
    reason: d.reasons.includes("REPORTED") ? "must" : "low",
    kind: `혜택 정책 · ${BENEFIT_SOURCE[d.sourceCode ?? ""] ?? d.sourceCode ?? "정책"}`,
    title: r.source.title,
    source: r.source.agency ?? BENEFIT_SOURCE[d.sourceCode ?? ""] ?? "-",
    version: `v${d.rawVersion}`,
    received: when(d.queuedAt),
    age: ago(d.queuedAt),
    paras: [
      {
        head: "검수 이유",
        parts: [
          {
            t: d.reasons.map((r) => issueText(r, null)).join(" / ") || "이유 코드가 없어요",
            kind: "low" as SourcePartKind,
          },
        ],
      },
      ...paras,
    ],
    fields: rows,
    impact: r.relevant
      ? "확인 필요 표시가 풀린 정제 결과가 다시 나가요 (알림 없음)"
      : "주거 혜택이 아니라고 판정된 정책이에요",
    log: [
      {
        at: when(d.queuedAt),
        who: "시스템",
        text: `검수 대기열에 추가 (${d.reasons.map((r) => issueText(r, null)).join(" / ")})`,
      },
    ],
  };
}

/** 대기열 한 줄: 목록 응답만으로 만들어요. 원문·추출 결과는 고른 건만 {@link liveReviewDetail}로 받아요 */
const ROW = { paras: [], fields: [], impact: "-", log: [] } satisfies Partial<ReviewItem>;
/** 혜택 상세 응답에는 출처 코드가 없어 대기열 목록에서 기억해 둬요 */
const benefitSourceCodes = new Map<string, string | null>();

type ReviewQueuePage = {
  total: number;
  items: {
    kind: "NOTICE" | "BENEFIT";
    id: string;
    reason: string;
    title: string | null;
    sourceCode: string | null;
    rawVersion: number | null;
    queuedAt: string | null;
  }[];
  nextCursor: string | null;
};
/** 화면의 사유 → 대기열 API의 reason */
const REVIEW_REASON_API: Record<ReviewReason, string> = {
  must: "MUST",
  low: "CHECK",
  format: "FORMAT",
};
/** 대기열 한 번에 받는 건수 (백엔드 최대 100) */
const QUEUE_PAGE_SIZE = 20;

/**
 * 검수 대기열 한 페이지: 공고·혜택 검수를 들어온 시각 순으로 섞어 20건씩 받아요(무한 스크롤). 원문·추출 결과는 고른 건만
 * {@link liveReviewDetail}로 받아요. kinds는 내 권한으로 볼 수 있는 종류(NOTICE·BENEFIT)예요
 */
export async function liveReviewQueuePage(
  kinds: string[],
  reason: ReviewReason | null,
  cursor: string | null,
): Promise<{ total: number; items: ReviewItem[]; nextCursor: string | null }> {
  const q = new URLSearchParams({ kinds: kinds.join(","), size: String(QUEUE_PAGE_SIZE) });
  if (reason) q.set("reason", REVIEW_REASON_API[reason]);
  if (cursor) q.set("cursor", cursor);
  const page = await api.get<ReviewQueuePage>(`/api/admin/reviews/queue?${q}`);
  const items = page.items.map((i): ReviewItem => {
    const benefit = i.kind === "BENEFIT";
    const id = `${benefit ? "b" : "n"}:${i.id}`;
    if (benefit) benefitSourceCodes.set(id, i.sourceCode);
    const source = benefit
      ? (BENEFIT_SOURCE[i.sourceCode ?? ""] ?? i.sourceCode ?? "정책")
      : (i.sourceCode ?? "-").toUpperCase();
    return {
      ...ROW,
      id,
      reason: REASON[i.reason] ?? "low",
      kind: benefit ? `혜택 정책 · ${source}` : "공고",
      title: i.title ?? "(제목 없음)",
      source,
      version: i.rawVersion != null ? `v${i.rawVersion}` : "-",
      received: when(i.queuedAt),
      age: ago(i.queuedAt),
    };
  });
  return { total: page.total, items, nextCursor: page.nextCursor };
}

/** 고른 검수 건 하나의 원문·추출 결과 (승인·반려에 쓰는 칸 정보도 이때 채워요) */
export async function liveReviewDetail(itemId: string): Promise<ReviewItem> {
  const id = itemId.slice(2);
  if (itemId.startsWith("n:")) {
    return noticeItem(await api.get<NoticeReviewDetail>(`/api/admin/reviews/${id}`));
  }
  const d = await api.get<BenefitReviewDetail>(`/api/admin/benefit-reviews/${id}`);
  return benefitItem({ ...d, sourceCode: benefitSourceCodes.get(itemId) ?? null });
}

export const EMPTY_REVIEW: ReviewItem = {
  id: "empty",
  reason: "low",
  kind: "-",
  title: "검수할 항목이 없어요",
  source: "-",
  version: "-",
  received: "-",
  age: "",
  paras: [],
  fields: [],
  impact: "-",
  log: [],
};

/** 승인·반려. edits는 화면 칸 이름 → 새 글자. */
export async function decideReview(
  itemId: string,
  approve: boolean,
  edits: Record<string, string>,
  rejectReason: string | null,
) {
  const meta = reviewMeta.get(itemId);
  if (!meta) throw new Error("검수 항목 정보가 없어요. 새로고침해 주세요");
  const body: Record<string, unknown> = {};
  if (approve) {
    const list = Object.entries(edits).flatMap(([label, text]) => {
      const f = meta.fields[label];
      // 예전에는 고칠 수 없는 칸의 수정을 조용히 버리고 「수정 후 승인」이라고 했어요. 보내기 전에 알려요
      if (!f || !f.editable)
        throw new Error(`「${label}」 칸은 여기서 고칠 수 없어요. 원문과 다르면 반려해 주세요`);
      let value: unknown = text;
      if (f.json) {
        try {
          value = text.trim() === "" ? null : JSON.parse(text);
        } catch {
          if (meta.kind === "benefit" && f.path.startsWith("/conditions/"))
            throw new Error(`「${label}」 값은 {"max":6000,…} 같은 JSON 형식이어야 해요`);
          value = text;
        }
      }
      const one = [{ path: f.path, value }];
      if (meta.kind === "benefit" && f.path.startsWith("/conditions/"))
        one.push({ path: f.path.replace(/\/value$/, "/known"), value: value != null });
      return one;
    });
    if (list.length) body.edits = list;
  } else if (rejectReason) {
    body.reason = REJECT[rejectReason] ?? null;
  }
  const base = meta.kind === "notice" ? "/api/admin/reviews/" : "/api/admin/benefit-reviews/";
  return api.post<{ pendingCount: number }>(
    `${base}${meta.id}/${approve ? "approve" : "reject"}`,
    body,
  );
}

const REJECT: Record<string, string> = {
  "중복 공고": "DUPLICATE",
  "원문과 다름": "SOURCE_MISMATCH",
  "서비스 대상 아님": "OUT_OF_SCOPE",
  "마감된 공고": "CLOSED",
};

// ---------- 제보 ----------
const reportTargetLabel: Record<string, string> = {
  NOTICE: "공고",
  BENEFIT: "혜택 정책",
  PROGRAM: "창업지원·사업공간",
  GENERAL: "일반 제보",
};
/** 일반 제보 종류 (백엔드 field) */
const generalKindLabel: Record<string, string> = {
  MISSING_NOTICE: "빠진 공고·정책",
  WRONG_INFO: "틀린 정보",
  APP_ERROR: "화면 오류",
  ETC: "기타",
};
type ReportList = {
  counts: { newCount: number; doing: number; done: number };
  items: {
    id: string;
    status: string;
    screen: string | null;
    targetType: string;
    noticeId: string | null;
    /** 창업지원 사업 제보면 사업 ID (사업 지원 상세 /business/support/{id}) */
    programId: string | null;
    /** 혜택 제보의 원본 정책 ID (혜택 검수용) */
    benefitPolicyId: string | null;
    /** 혜택 화면(/benefits/{id})용 혜택 ID. 원본 정책 ID와 달라요. 아직 저장 전이면 null */
    benefitId: string | null;
    /** 일반 제보(GENERAL)는 null */
    noticeTitle: string | null;
    field: string;
    currentValue: string | null;
    reportedValue: string | null;
    summary: string | null;
    createdAt: string;
    groupCount: number;
  }[];
};
type ReportDetail = {
  note: string | null;
  notes: { text: string; createdAt: string }[];
  reply: string | null;
  reviewId: string | null;
};

const STATUS: Record<string, ReportStatus> = { NEW: "new", DOING: "doing", DONE: "done" };

export async function liveReports(): Promise<{
  doneBefore: number;
  newBefore: number;
  items: ReportItem[];
}> {
  // 상세(제보 설명·같은 묶음 설명·답장)는 고른 제보만 받아요(liveReportDetail). 목록마다 상세를 다 받으면 요청이 100번 넘게 나가요
  const list = await api.get<ReportList>("/api/admin/reports");
  const items: (ReportItem & { at: string })[] = list.items.map((r) => ({
    at: r.createdAt,
    id: r.id,
    st: STATUS[r.status] ?? "new",
    where: `${r.screen ?? "-"} · ${reportTargetLabel[r.targetType] ?? "공고"}`,
    target:
      r.targetType === "GENERAL"
        ? (generalKindLabel[r.field] ?? "일반 제보")
        : (r.noticeTitle ?? "-"),
    field: r.targetType === "GENERAL" ? (generalKindLabel[r.field] ?? r.field) : r.field,
    general: r.targetType === "GENERAL",
    current: r.currentValue ?? "-",
    reported: r.reportedValue ?? "-",
    source: r.summary ?? "-", // 화면에서는 「제보 설명」으로 보여요(기관 원문이 아님). 상세를 받으면 그 설명으로
    summary: r.summary ?? r.field,
    age: ago(r.createdAt),
    groupCount: r.groupCount,
    // 「원문 보기」: 공고 · 혜택(혜택 ID, 아직 없으면 혜택 목록) · 사업 지원 상세
    link: r.noticeId
      ? routes.notice(r.noticeId)
      : r.benefitPolicyId
        ? r.benefitId
          ? routes.benefit(r.benefitId)
          : routes.benefits
        : r.programId
          ? `${routes.bizSupport}/${r.programId}`
          : "",
    notes: [],
    reply: "",
  }));
  items.push(...(await liveAreaReports()));
  items.sort((a, b) => b.at.localeCompare(a.at)); // 공고·생활권 제보를 들어온 차례(최근 먼저)로
  return { doneBefore: 0, newBefore: 0, items };
}

// 생활권 제보(역까지 거리 등 공고 주변 정보). 공고 제보와 같은 목록에 섞어 보여 줘요. id 앞에 「area:」를 붙여 처리 API를 가려요
type AreaReportList = {
  counts: { newCount: number; doing: number; done: number };
  items: {
    id: string;
    status: string;
    screen: string | null;
    noticeId: string;
    noticeLocationId: string | null;
    field: string;
    currentValue: string | null;
    reportedValue: string | null;
    summary: string | null;
    createdAt: string;
    groupCount: number;
  }[];
};
type AreaReportDetail = {
  note: string | null;
  notes: { text: string; createdAt: string }[];
  reply: string | null;
};
const AREA_REPORT = "area:";
export const isAreaReport = (id: string) => id.startsWith(AREA_REPORT);

async function liveAreaReports(): Promise<(ReportItem & { at: string })[]> {
  const list = await api.get<AreaReportList>("/api/admin/area-reports");
  const [notices] = await Promise.all([
    // 생활권 제보는 공고 제목을 주지 않아 공고 상세에서 제목·단지 이름을 찾아요
    Promise.all(
      [...new Set(list.items.map((i) => i.noticeId))].map((id) =>
        api
          .get<{
            header: { title: string };
            sites: { id: string; name: string | null }[];
          }>(`/api/v1/notices/${id}`)
          .then((d) => [id, d] as const)
          .catch(() => [id, null] as const),
      ),
    ).then((rows) => new Map(rows)),
  ]);
  return list.items.map((r) => {
    const notice = notices.get(r.noticeId);
    const site = notice?.sites.find((s) => s.id === r.noticeLocationId)?.name;
    return {
      at: r.createdAt,
      id: AREA_REPORT + r.id,
      st: STATUS[r.status] ?? "new",
      where: `${r.screen ?? "-"} · 생활권`,
      target: [notice?.header.title ?? "공고", site].filter(Boolean).join(" · "),
      field: r.field,
      current: r.currentValue ?? "-",
      reported: r.reportedValue ?? "-",
      source: r.summary ?? "-",
      summary: r.summary ?? r.field,
      age: ago(r.createdAt),
      groupCount: r.groupCount,
      link: routes.notice(r.noticeId),
      notes: [],
      reply: "",
    };
  });
}

// ---------- 제보 대기열 (무한 스크롤) ----------
const REPORT_PAGE_SIZE = 20;
const REPORT_STATUS_API: Record<ReportStatus, string> = {
  new: "NEW",
  doing: "DOING",
  done: "DONE",
};

type ReportQueueApiPage = {
  items: {
    kind: "REPORT" | "AREA";
    id: string;
    status: string;
    screen: string | null;
    targetType: string;
    noticeId: string | null;
    programId: string | null;
    benefitPolicyId: string | null;
    benefitId: string | null;
    title: string | null;
    field: string;
    currentValue: string | null;
    reportedValue: string | null;
    summary: string | null;
    createdAt: string;
    groupCount: number;
  }[];
  nextCursor: string | null;
};

/**
 * 제보 대기열 한 페이지: 공고·혜택·사업 제보와 생활권 제보를 서버가 최신순으로 섞어 20건씩 줘요(상태마다 따로).
 * 설명·같은 묶음 설명·답장은 고른 제보만 받아요({@link liveReportDetail}).
 */
export async function liveReportQueuePage(
  status: ReportStatus,
  cursor: string | null,
): Promise<{ items: ReportItem[]; nextCursor: string | null }> {
  const q = new URLSearchParams({
    status: REPORT_STATUS_API[status],
    size: String(REPORT_PAGE_SIZE),
  });
  if (cursor) q.set("cursor", cursor);
  const page = await api.get<ReportQueueApiPage>(`/api/admin/reports/queue?${q}`);
  const items = page.items.map((r): ReportItem => {
    const area = r.kind === "AREA";
    const general = r.targetType === "GENERAL";
    return {
      id: area ? AREA_REPORT + r.id : r.id,
      st: STATUS[r.status] ?? "new",
      where: `${r.screen ?? "-"} · ${area ? "생활권" : (reportTargetLabel[r.targetType] ?? "공고")}`,
      target: general
        ? (generalKindLabel[r.field] ?? "일반 제보")
        : (r.title ?? (area ? "공고" : "-")),
      field: general ? (generalKindLabel[r.field] ?? r.field) : r.field,
      general,
      current: r.currentValue ?? "-",
      reported: r.reportedValue ?? "-",
      source: r.summary ?? "-", // 상세를 받으면 그 설명으로
      summary: r.summary ?? r.field,
      age: ago(r.createdAt),
      groupCount: r.groupCount,
      // 「원문 보기」: 공고 · 혜택(혜택 ID, 아직 없으면 혜택 목록) · 사업 지원 상세
      link: r.noticeId
        ? routes.notice(r.noticeId)
        : r.benefitPolicyId
          ? r.benefitId
            ? routes.benefit(r.benefitId)
            : routes.benefits
          : r.programId
            ? `${routes.bizSupport}/${r.programId}`
            : "",
      notes: [],
      reply: "",
    };
  });
  return { items, nextCursor: page.nextCursor };
}

/** 제보 상태별 건수: 공고·혜택·사업 제보와 생활권 제보를 더해요 */
export async function liveReportCounts(): Promise<{ new: number; doing: number; done: number }> {
  type Counts = { newCount: number; doing: number; done: number };
  const [r, a] = await Promise.all([
    api.get<Counts>("/api/admin/reports/counts"),
    api.get<Counts>("/api/admin/area-reports/counts").catch(() => null),
  ]);
  return {
    new: r.newCount + (a?.newCount ?? 0),
    doing: r.doing + (a?.doing ?? 0),
    done: r.done + (a?.done ?? 0),
  };
}

/**
 * 고른 제보 하나의 상세: 제보 설명(없으면 요약), 같은 묶음의 다른 제보 설명, 저장된 답장. 공고 제보·생활권 제보(id 앞 「area:」) 모두.
 * 목록은 이 값 없이 받고(요청 한 번), 화면이 고른 제보만 이걸로 채워요.
 */
export async function liveReportDetail(
  id: string,
  summary: string,
): Promise<Pick<ReportItem, "source" | "notes" | "reply">> {
  const d = isAreaReport(id)
    ? await api.get<AreaReportDetail>(`/api/admin/area-reports/${id.slice(AREA_REPORT.length)}`)
    : await api.get<ReportDetail>(`/api/admin/reports/${id}`);
  return {
    source: d.note ?? summary,
    notes: (d.notes ?? []).map((n) => ({ text: n.text, meta: `사용자 · ${when(n.createdAt)}` })),
    reply: d.reply ?? "",
  };
}

/** 처리 끝: 고침(FIXED)·그대로(KEPT)와 답장. 처리 시작 전이면 먼저 시작해요. */
export async function resolveReport(id: string, fixed: boolean, reply: string) {
  const path = isAreaReport(id)
    ? `/api/admin/area-reports/${id.slice(AREA_REPORT.length)}/resolve`
    : `/api/admin/reports/${id}/resolve`;
  return api.post(path, {
    result: fixed ? "FIXED" : "KEPT",
    reply: reply.trim() || null,
  });
}

/** 다시 검수로 보내기(고치기): 공고·혜택 정책의 검수를 다시 열어요. */
export async function reopenFromReport(id: string) {
  if (isAreaReport(id)) throw new Error("생활권 제보는 AI 추출 값이 아니라 검수로 보낼 수 없어요");
  return api.post<{ reviewId: string; reopened: boolean }>(`/api/admin/reports/${id}/review`);
}

// ---------- 사이드바 숫자·개요 ----------
export async function liveCounts(): Promise<AdminCounts> {
  // 숫자마다 따로 받아요. 추출·수집 서비스가 꺼져 있어도 다른 숫자는 보이고, 못 받은 숫자는 0 대신 비워요(null)
  const settle = <T>(p: Promise<T>) => p.catch(() => null);
  const [n, b, r, area, src, chat, dup] = await Promise.all([
    settle(api.get<{ reviewPending: number }>("/api/admin/reviews/counts")),
    // 혜택은 건수만 받아요(목록 전체를 받아 세지 않게)
    settle(api.get<{ benefitPending: number }>("/api/admin/benefit-reviews/counts")),
    settle(api.get<{ newCount: number }>("/api/admin/reports/counts")),
    settle(api.get<{ newCount: number }>("/api/admin/area-reports/counts")),
    settle(api.get<CollectorStatus>("/api/admin/sources")),
    // 채팅 신고는 숫자 API만 받아요(신고 100건을 받아 글 수를 세지 않게)
    settle(api.get<{ pendingMessages: number }>("/api/admin/chat/reports/counts")),
    settle(api.get<{ pending: number }>("/api/admin/policy-duplicates/counts")),
  ]);
  return {
    reviewPending: n && b ? n.reviewPending + b.benefitPending : null,
    sourceIssues: src ? src.summary.fail + src.summary.late + src.summary.paused : null,
    newReports: r ? r.newCount + (area?.newCount ?? 0) : null,
    chatReports: chat ? chat.pendingMessages : null,
    policyDuplicates: dup ? dup.pending : null,
  };
}

export async function liveOverview(base: AdminOverview): Promise<AdminOverview> {
  // 숫자마다 따로 받아요. 하나가 실패해도(서버 꺼짐·권한 없음) 나머지는 보이고, 실패한 카드만 「불러오지 못했어요」
  const none = () => null;
  const [n, b, r, urgent, stats, handled, ar, collected] = await Promise.all([
    api
      .get<{ reviewPending: number; oldestReceivedAt: string | null }>("/api/admin/reviews/counts")
      .catch(none),
    api.get<{ benefitPending: number }>("/api/admin/benefit-reviews/counts").catch(none),
    api
      .get<{ newCount: number; doing: number; done: number }>("/api/admin/reports/counts")
      .catch(none),
    api
      .get<{ id: string; title: string; applyEndsOn: string | null }[]>(
        "/api/admin/reviews/urgent?days=3",
      )
      .catch(none),
    api
      .get<{
        recent: {
          asIsRate: number | null;
          editedRate: number | null;
          rejectedRate: number | null;
          medianMinutes: number | null;
        };
        today: { approved: number; editedApproved: number; rejected: number };
      }>("/api/admin/reviews/stats?days=7")
      .catch(none),
    // 「제보로 고친 값」은 최근 7일에 고침(FIXED)으로 끝낸 제보, 「오늘 제보 답변」은 오늘 끝낸 제보예요(그대로 둠 포함)
    doneReports().catch(none),
    // 생활권 제보도 제보 수에 더해요
    api
      .get<{ newCount: number; doing: number; done: number }>("/api/admin/area-reports/counts")
      .catch(none),
    collectedSummary(),
  ]);
  const FAILED = "불러오지 못했어요";
  // 백엔드가 이미 0~100 정수로 줘요(예전에 100을 또 곱해 75%가 7500%로 보였음)
  const pct = (v: number | null | undefined) => (v == null ? "-" : `${v}%`);
  const reports = r
    ? {
        newCount: r.newCount + (ar?.newCount ?? 0),
        doing: r.doing + (ar?.doing ?? 0),
        done: r.done + (ar?.done ?? 0),
      }
    : null;
  const isPast = (d: string | null) => !!d && d < new Date().toLocaleDateString("en-CA");
  const todos: AdminTodo[] = [
    // 마감 전(3일 안)인 건을 먼저, 이미 마감된 대기 건은 뒤에
    ...[...(urgent ?? [])]
      .sort((a, c) => Number(isPast(a.applyEndsOn)) - Number(isPast(c.applyEndsOn)))
      .slice(0, 4)
      .map((u) => ({
        id: u.id,
        kind: "deadline" as const,
        title: u.title,
        // 백엔드는 마감이 이미 지난 대기 건도 함께 줘요(먼저 정리할 일). 지났으면 그렇게 표시해요
        desc: `${u.applyEndsOn && u.applyEndsOn < new Date().toLocaleDateString("en-CA") ? "마감 지남" : "마감"} ${u.applyEndsOn} · 검수 대기`,
      })),
    ...(reports?.newCount
      ? [
          {
            id: "reports",
            kind: "report" as const,
            title: `새 제보 ${reports.newCount}건`,
            desc: "제보 화면에서 확인해요",
          },
        ]
      : []),
  ];
  return {
    ...base,
    asOf: new Date().toLocaleString("ko-KR", {
      timeZone: KST,
      month: "long",
      day: "numeric",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
    }),
    review: n
      ? { count: n.reviewPending + (b?.benefitPending ?? 0), oldest: span(n.oldestReceivedAt) }
      : { count: null, oldest: FAILED },
    reports: reports
      ? {
          count: reports.newCount + reports.doing,
          note: `새 ${reports.newCount} · 처리 중 ${reports.doing} · 끝 ${reports.done}`,
        }
      : { count: null, note: FAILED },
    collected: collected
      ? {
          count: collected.today,
          note: `최근 회차 새 글 ${collected.recent}건 · 누적 ${collected.total.toLocaleString("ko-KR")}건`,
        }
      : { count: null, note: `${FAILED} (수집기 연결 안 됨)` },
    issues: collected
      ? {
          count: collected.fail + collected.late,
          note: `실패 ${collected.fail} · 지연·중지 ${collected.late}`,
        }
      : { count: null, note: `${FAILED} (수집기 연결 안 됨)` },
    todos: todos.length ? todos : base.todos.slice(0, 0),
    quality: {
      ...base.quality,
      asIs: pct(stats?.recent.asIsRate),
      edited: pct(stats?.recent.editedRate),
      rejected: pct(stats?.recent.rejectedRate),
      medianTime: stats?.recent.medianMinutes == null ? "-" : `${stats.recent.medianMinutes}분`,
      fixedByReport: handled ? `${handled.fixed7}건` : "-",
    },
    today: {
      approved: stats?.today.approved ?? null,
      editedApproved: stats?.today.editedApproved ?? null,
      rejected: stats?.today.rejected ?? null,
      replied: handled?.today ?? null,
    },
  };
}

/** 끝난 공고·생활권 제보의 처리 시각으로 최근 7일 고친 수·오늘 끝낸 수를 세요. */
async function doneReports(): Promise<{ fixed7: number; today: number }> {
  type Done = { items: { id: string; result: string | null }[] };
  const [n, a] = await Promise.all([
    api.get<Done>("/api/admin/reports?status=DONE").catch(() => ({ items: [] }) as Done),
    api.get<Done>("/api/admin/area-reports?status=DONE").catch(() => ({ items: [] }) as Done),
  ]);
  const at = await Promise.all([
    ...n.items.map((i) =>
      api
        .get<{ handledAt: string | null }>(`/api/admin/reports/${i.id}`)
        .then((d) => ({ result: i.result, at: d.handledAt })),
    ),
    ...a.items.map((i) =>
      api
        .get<{ handledAt: string | null }>(`/api/admin/area-reports/${i.id}`)
        .then((d) => ({ result: i.result, at: d.handledAt })),
    ),
  ]);
  const weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
  const today = new Date().toLocaleDateString("en-CA", { timeZone: KST });
  return {
    fixed7: at.filter((x) => x.result === "FIXED" && x.at && Date.parse(x.at) >= weekAgo).length,
    today: at.filter(
      (x) => x.at && new Date(x.at).toLocaleDateString("en-CA", { timeZone: KST }) === today,
    ).length,
  };
}

// ---------- 수집 현황 (수집기 관리자 API를 api 서버가 대신 불러요) ----------
type CollectorRun = {
  startedAt: string;
  finishedAt: string | null;
  status: string;
  newCount: number | null;
  error: string | null;
};
type CollectorSource = {
  code: string;
  name: string;
  enabled: boolean;
  state: string;
  lastRun: CollectorRun | null;
  lastSuccessAt: string | null;
  consecutiveEmpty: number;
  consecutiveFailures: number;
  totalCollected: number;
  recentRuns: CollectorRun[];
};
export type CollectorStatus = {
  asOf: string;
  summary: { ok: number; late: number; fail: number; paused: number };
  sources: CollectorSource[];
};

const POLICY_SOURCES = new Set([
  "youth",
  "bizinfo",
  "kstartup",
  "gov24",
  "bokjiro_central",
  "bokjiro_local",
]);
const AREA: Record<string, string> = {
  lh: "주거 · 전국",
  sh: "주거 · 서울",
  gh: "주거 · 경기",
  ih: "주거 · 인천",
  bmc: "주거 · 부산",
  dcco: "주거 · 대전",
  dudc: "주거 · 대구",
  gbdc: "주거 · 경북",
  gndc: "주거 · 경남",
  umca: "주거 · 울산",
  soco: "주거 · 서울 청년안심주택",
  youth: "청년정책 · 전국",
  bizinfo: "창업 · 전국",
  kstartup: "창업 · 전국",
  gov24: "혜택 · 전국",
  bokjiro_central: "복지 · 중앙부처",
  bokjiro_local: "복지 · 지자체",
};

export async function liveSources() {
  const s = await api.get<CollectorStatus>("/api/admin/sources");
  const rows: SourceRow[] = s.sources.map((src) => {
    const policy = POLICY_SOURCES.has(src.code);
    const st: SourceStatus =
      src.consecutiveFailures > 0 ||
      src.lastRun?.status === "FAILED" ||
      src.lastRun?.status === "BLOCKED"
        ? "fail"
        : src.state === "ok" ||
            // 일시 중지한 곳은 중지 표시를 따로 하고(화면), 여기서는 마지막 수집 결과로 봐요. 다시 켠 직후 「지연」으로 잠깐 보이지 않게
            (src.state === "paused" && src.lastRun?.status === "SUCCESS")
          ? "ok"
          : "late";
    const issue = !src.enabled
      ? "일시 중지한 출처예요"
      : src.consecutiveFailures > 0
        ? `연속 ${src.consecutiveFailures}번 실패했어요${src.lastRun?.error ? " · " + src.lastRun.error.split("\n")[0] : ""}`
        : src.lastRun?.status === "BLOCKED"
          ? "수집이 막혔어요(robots.txt·접근 차단)"
          : !src.lastRun
            ? "아직 한 번도 수집하지 않았어요"
            : src.state !== "ok"
              ? `마지막 성공이 ${ago(src.lastSuccessAt)}이에요`
              : undefined;
    return {
      id: src.code,
      name: src.name,
      area: AREA[src.code] ?? "-",
      method: policy || src.code === "lh" ? "공공 API" : "게시판",
      cycle: policy ? "매일 06:30" : "평일 9~18시 매시간",
      last: src.lastRun ? when(src.lastRun.startedAt) : "-",
      count: src.lastRun?.newCount ?? 0,
      st,
      issue,
      runs: src.recentRuns.slice(0, 6).map((r) => ({
        at: when(r.startedAt),
        text: `${r.newCount ?? 0}건 · ${RUN_KO[r.status] ?? r.status}${r.error ? " · " + r.error.split("\n")[0].slice(0, 60) : ""}`,
        tone: (r.status === "FAILED"
          ? "fail"
          : r.status === "RUNNING"
            ? "late"
            : "normal") as SourceRun["tone"],
      })),
      robots: "-",
      parser: policy ? "API 응답" : "목록·상세 화면",
      total: `${src.totalCollected.toLocaleString("ko-KR")}건`,
    };
  });
  return {
    total: rows.length,
    asOf: when(s.asOf),
    summary: { ok: s.summary.ok, late: s.summary.late + s.summary.paused, fail: s.summary.fail },
    rows,
    enabled: Object.fromEntries(s.sources.map((x) => [x.code, x.enabled])) as Record<
      string,
      boolean
    >,
  };
}

export const sourceAction = (code: string, action: "run" | "pause" | "resume") =>
  api.post(`/api/admin/sources/${code}/${action}`);

// ---------- 기준값 ----------
type CriteriaYears = {
  years: {
    year: number;
    validFrom: string;
    state: string;
    data: { monthlyWon?: Record<string, number> };
    source: string | null;
    updatedAt: string;
  }[];
};
type CriteriaHistory = {
  kind: string;
  changes: {
    year: number;
    validFrom: string;
    source: string | null;
    replacedAt: string;
    replacedBy: string | null;
  }[];
};
type Usage = { housing: number; businessSpace: number; startupSupport: number; total: number };
export async function liveCriteria(base: AdminCriteria): Promise<AdminCriteria> {
  const [median, mHist, mUse, uUse, rUse] = await Promise.all([
    api.get<CriteriaYears>("/api/admin/criteria/MEDIAN_INCOME"),
    api
      .get<CriteriaHistory>("/api/admin/criteria/MEDIAN_INCOME/history")
      .catch(() => ({ kind: "", changes: [] }) as CriteriaHistory),
    api.get<Usage>("/api/admin/criteria/MEDIAN_INCOME/usage"),
    api.get<Usage>("/api/admin/criteria/URBAN_WORKER_INCOME/usage"),
    api.get<Usage>("/api/admin/criteria/RANK_CRITERIA/usage"),
  ]);
  const current = median.years.find((y) => y.state === "IN_EFFECT") ?? median.years[0];
  const monthly = current?.data.monthlyWon ?? {};
  const incomeBase = Object.keys(monthly)
    .sort((a, b) => Number(a) - Number(b))
    .map((k) => monthly[k]);
  const usage = (name: string, u: Usage) =>
    [
      u.housing ? { name: `${name} · 주거 공고`, ratio: `판정 틀 ${u.housing}개` } : null,
      u.businessSpace
        ? { name: `${name} · 사업공간`, ratio: `판정 틀 ${u.businessSpace}개` }
        : null,
      u.startupSupport
        ? { name: `${name} · 창업지원 사업`, ratio: `판정 틀 ${u.startupSupport}개` }
        : null,
    ].filter((x): x is { name: string; ratio: string } => x !== null);
  // 이 탭은 기준 중위소득 화면이라 그 값을 쓰는 판정 틀만 세요. 다른 기준값은 「참고」로 따로 적어요(숫자에 섞지 않게)
  const other = [...usage("도시근로자 월평균소득", uUse), ...usage("순위 요건", rUse)].map((r) => ({
    ...r,
    name: `참고 · ${r.name}`,
  }));
  const rules = [...usage("기준 중위소득", mUse), ...other];
  return {
    ...base,
    incomeBase,
    rulesCount: mUse.total,
    rules,
    history: [
      ...median.years.map((y) => ({
        title: `${y.year}년 값 ${y.state === "IN_EFFECT" ? "적용 중" : y.state === "SCHEDULED" ? "적용 예약" : "지난 값"}`,
        meta: `${y.validFrom}부터 · ${y.source ?? "근거 없음"}`,
      })),
      ...mHist.changes.map((h) => ({
        title: `${h.year}년 값 바뀜`,
        meta: `${when(h.replacedAt)} · ${h.source ?? ""}`,
      })),
    ],
    score: { ...base.score, lastChecked: "판정 코드" },
    // 「지역 구분」은 수도권 과밀억제권역(수도권정비계획법 시행령 별표 1) 법정 목록이에요. 백엔드에 저장소가 없어 화면 목록을 그대로 써요.
    // 규제지역(투기과열·조정대상)은 별도 관리 API(/api/admin/regulated-areas)에 있어요
    regions: base.regions,
  };
}

/** 다음 해 기준 중위소득 적용 예약 (그해 1월 1일 0시부터 판정에 쓰여요) */
export const scheduleMedianIncome = (
  year: number,
  monthlyWon: Record<string, number>,
  source: string,
) =>
  api.put(`/api/admin/criteria/MEDIAN_INCOME/${year}`, {
    validFrom: `${year}-01-01`,
    data: { monthlyWon },
    source,
  });

/** 개요의 수집 칸 */
/** 수집 현황 요약. 수집기에 연결하지 못하거나 권한이 없으면 null (0으로 보이지 않게) */
export async function collectedSummary() {
  const src = await api.get<CollectorStatus>("/api/admin/sources").catch(() => null);
  if (!src) return null;
  const todayKst = new Date().toLocaleDateString("ko-KR", { timeZone: KST });
  const sources = src.sources;
  return {
    today: sources
      .flatMap((x) => x.recentRuns)
      .filter(
        (x) => new Date(x.startedAt).toLocaleDateString("ko-KR", { timeZone: KST }) === todayKst,
      )
      .reduce((a, x) => a + (x.newCount ?? 0), 0),
    recent: sources.reduce((a, x) => a + (x.lastRun?.newCount ?? 0), 0),
    total: sources.reduce((a, x) => a + x.totalCollected, 0),
    fail: src.summary.fail,
    late: src.summary.late + (src.summary.paused ?? 0),
  };
}

// ---------- 트래픽 (백엔드 traffic 모듈) ----------
export function liveTraffic(days: number) {
  return api.get<TrafficData>(`/api/admin/traffic?days=${days}`);
}

export function liveRealtime() {
  return api.get<RealtimeData>("/api/admin/traffic/realtime");
}

export function liveBotTraffic(days: number) {
  return api.get<BotTrafficData>(`/api/admin/traffic/bots?days=${days}`);
}

// ---------- 채팅 신고 (백엔드 chat 모듈) ----------
type ChatReportPage = { items: ChatReport[]; nextCursor: string | null; hasNext: boolean };

const chatReportPage = (status: ChatReviewStatus, cursor?: string, size = 100) =>
  api.get<ChatReportPage>(
    `/api/admin/chat/reports?status=${status}&size=${size}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
  );

/**
 * 채팅 신고 한 페이지(20건, 무한 스크롤)와 그 페이지에 나온 공고의 제목. 화면은 받아 둔 페이지를 모두 모아 글마다 묶어요
 * ({@link groupChatReports}): 한 글의 신고가 다음 페이지에 이어지면 그 글 묶음에 더해져요.
 */
export async function liveChatReportPage(status: ChatReviewStatus, cursor: string | null) {
  const page = await chatReportPage(status, cursor ?? undefined, 20);
  const titles = await noticeTitles([...new Set(page.items.map((r) => r.noticeId))]);
  return { reports: page.items, titles, nextCursor: page.hasNext ? page.nextCursor : null };
}

/** 상태별 신고를 모두 받아요(한 번에 100건, 최대 500건) */
async function allChatReports(status: ChatReviewStatus) {
  const all: ChatReport[] = [];
  let cursor: string | undefined;
  for (let i = 0; i < 5; i++) {
    const page = await chatReportPage(status, cursor);
    all.push(...page.items);
    if (!page.hasNext || !page.nextCursor) break;
    cursor = page.nextCursor;
  }
  return all;
}

/** 신고 응답에는 공고 ID만 있어요. 화면에 보일 공고 제목을 공고 상세에서 찾아요(못 찾으면 비움) */
export async function noticeTitles(ids: string[]) {
  const pairs = await Promise.all(
    ids.map((id) =>
      api
        .get<{ header: { title: string } }>(`/api/v1/notices/${id}`)
        .then((d) => [id, d.header.title] as const)
        .catch(() => [id, null] as const),
    ),
  );
  return Object.fromEntries(pairs.filter((p) => p[1] !== null)) as Record<string, string>;
}

/** 신고를 메시지별로 묶어요. 최근에 신고가 들어온 메시지부터 */
export function groupChatReports(
  reports: ChatReport[],
  titles: Record<string, string>,
): ChatReportGroup[] {
  const groups = new Map<string, ChatReportGroup>();
  for (const r of reports) {
    const g = groups.get(r.messageId) ?? {
      messageId: r.messageId,
      noticeId: r.noticeId,
      noticeTitle: titles[r.noticeId] ?? null,
      message: r.message,
      reports: [],
      lastReportedAt: r.reportedAt,
    };
    g.reports.push({
      reportId: r.reportId,
      reason: r.reason,
      detail: r.detail,
      reportedAt: r.reportedAt,
    });
    if (r.reportedAt > g.lastReportedAt) g.lastReportedAt = r.reportedAt;
    groups.set(r.messageId, g);
  }
  return [...groups.values()].sort((a, b) => b.lastReportedAt.localeCompare(a.lastReportedAt));
}

export async function liveChatReports(status: ChatReviewStatus) {
  const reports = await allChatReports(status);
  const titles = await noticeTitles([...new Set(reports.map((r) => r.noticeId))]);
  return groupChatReports(reports, titles);
}

/** 가림 유지(KEEP_HIDDEN) 또는 다시 보이기(RESTORE). 그 메시지의 검토 전 신고가 모두 처리돼요 */
export const reviewChatMessage = (messageId: string, action: ChatReviewAction) =>
  api.patch(`/api/admin/chat/messages/${messageId}`, { action });

// ---------- 회원 관리 (백엔드 user 모듈) ----------
export function liveUsers(query: string, filter: AdminUserFilter, page: number) {
  const q = new URLSearchParams({ page: String(page) });
  if (query.trim()) q.set("query", query.trim());
  if (filter) q.set("filter", filter);
  return api.get<AdminUsersPage>(`/api/admin/users?${q}`);
}

/** 이름만 (처리 기록의 관리자 이름). 최대 100명, 관리자 누구나 */
export function liveUserNames(ids: string[]) {
  return api.get<AdminUserName[]>(`/api/admin/users/names?ids=${ids.slice(0, 100).join(",")}`);
}

/** 관리자 지정(ADMIN)·해제(USER) — 「관리자 지정」 */
export const changeUserRole = (id: string, role: "USER" | "ADMIN") =>
  api.patch<AdminUser>(`/api/admin/users/${id}/role`, { role });

/** 일반 관리자의 권한을 이 목록으로 맞춰요 — 「권한 부여」, 내가 가진 권한만 */
export const setUserPermissions = (id: string, permissions: AdminPermission[]) =>
  api.put<AdminUser>(`/api/admin/users/${id}/permissions`, { permissions });

/** 이용 정지 (until 비우면 해제할 때까지) — 「이용 정지」 */
export const suspendUser = (id: string, reason: string, until: string | null) =>
  api.put<AdminUser>(`/api/admin/users/${id}/suspension`, { reason, until });

export const unsuspendUser = (id: string) =>
  api.delete<AdminUser>(`/api/admin/users/${id}/suspension`);

/** 최상위 관리자 넘기기 — 최상위만, 로그인한 지 10분 안에 */
export const transferSuperAdmin = (userId: string) =>
  api.post<AdminUser>("/api/admin/super/transfer", { userId });

/** 관리자 긴급 정지·풀기 — 최상위만 */
export const freezeAdmins = (reason: string) => api.put("/api/admin/super/freeze", { reason });
export const unfreezeAdmins = () => api.delete("/api/admin/super/freeze");

export function liveAdminChanges(days: number) {
  return api.get<AdminChange[]>(`/api/admin/users/changes?days=${days}`);
}

// ---------- 처리 기록 ----------
type CriteriaChanges = {
  kind: string;
  changes: {
    year: number;
    validFrom: string;
    source: string | null;
    replacedAt: string;
    replacedBy: string | null;
  }[];
};

const CRITERIA_KINDS: Record<string, string> = {
  MEDIAN_INCOME: "기준중위소득",
  URBAN_WORKER_INCOME: "도시근로자 월평균소득",
  RANK_CRITERIA: "순위 요건",
};

/** 검수·제보 처리(notice) + 기준값 바꾼 기록(eligibility) + 권한 변경(user)을 최근 순으로 합쳐요. 하나가 실패해도 나머지는 보여요 */
/** GET /api/admin/notifications/stats (알림 서버 발송 결과 + 알림함 지표) */
/** GET /api/admin/policy-duplicates?status= (중복 의심 사업 쌍 · 상태별 건수) */
export function livePolicyDuplicates(status: DuplicateStatus): Promise<DuplicateList> {
  return api.get<DuplicateList>(`/api/admin/policy-duplicates?status=${status}`);
}

/** 「둘 다 둠」(KEEP_BOTH) 또는 「나중 것 숨김」(HIDE_LATER) */
export const decidePolicyDuplicate = (
  later: string,
  earlier: string,
  action: "KEEP_BOTH" | "HIDE_LATER",
) => api.post(`/api/admin/policy-duplicates/${later}/${earlier}/decide`, { action });

export function liveNotificationStats(days: number): Promise<NotificationStats> {
  return api.get<NotificationStats>(`/api/admin/notifications/stats?days=${days}`);
}

export async function liveActivity(days: number): Promise<ActivityData> {
  const since = Date.now() - days * 86_400_000;
  const [main, criteria, roles, chatKept, chatRestored] = await Promise.all([
    api
      .get<{ items: (ActivityItem & { targetId: string | null })[]; reviewsError: string | null }>(
        `/api/admin/activity?days=${days}`,
      )
      .catch(() => null),
    Promise.all(
      Object.keys(CRITERIA_KINDS).map((k) =>
        api.get<CriteriaChanges>(`/api/admin/criteria/${k}/history`).catch(() => null),
      ),
    ),
    liveAdminChanges(days).catch(() => null),
    // 채팅 신고 처리 (처리한 관리자는 reviewedBy). 권한이 없거나 채팅이 없으면 빈 목록
    allChatReports("KEPT_HIDDEN").catch(() => [] as ChatReport[]),
    allChatReports("RESTORED").catch(() => [] as ChatReport[]),
  ]);
  const items: ActivityItem[] = [...(main?.items ?? [])];
  for (const h of criteria) {
    for (const c of h?.changes ?? []) {
      if (Date.parse(c.replacedAt) < since) continue;
      items.push({
        at: c.replacedAt,
        kind: "CRITERIA",
        action: "REPLACED",
        title: `${CRITERIA_KINDS[h!.kind] ?? h!.kind} ${c.year}년`,
        detail: c.source,
        by: c.replacedBy,
      });
    }
  }
  for (const r of roles ?? []) {
    items.push({
      at: r.changedAt,
      kind: "ROLE",
      action: r.kind,
      title:
        r.kind === "FREEZE" || r.kind === "UNFREEZE"
          ? "모든 관리자"
          : (r.nickname ?? "탈퇴한 회원"),
      detail: r.permission ? PERMISSION_INFO[r.permission].label : r.note,
      by: r.changedBy,
    });
  }
  // 같은 메시지의 신고는 한 번에 처리돼서 메시지마다 한 줄로 모아요
  const chat = new Map<string, { r: ChatReport; count: number }>();
  for (const r of [...chatKept, ...chatRestored]) {
    if (!r.reviewedAt || Date.parse(r.reviewedAt) < since) continue;
    const seen = chat.get(r.messageId);
    chat.set(r.messageId, { r: seen?.r ?? r, count: (seen?.count ?? 0) + 1 });
  }
  for (const { r, count } of chat.values()) {
    const text = (r.message.content ?? "").trim();
    items.push({
      at: r.reviewedAt!,
      kind: "CHAT_REPORT",
      action: r.reviewStatus,
      title: text ? (text.length > 40 ? `${text.slice(0, 40)}…` : text) : "지운 메시지",
      detail: `신고 ${count}건${r.message.authorNickname ? ` · 쓴 사람 ${r.message.authorNickname}` : ""}`,
      by: r.reviewedBy ?? null,
    });
  }
  items.sort((a, b) => b.at.localeCompare(a.at));
  const failed = [main ? null : "검수·제보", roles ? null : "관리자 변경"].filter(Boolean);
  return {
    items,
    reviewsError:
      main?.reviewsError ?? (failed.length ? `${failed.join("·")} 기록을 불러오지 못했어요` : null),
  };
}
