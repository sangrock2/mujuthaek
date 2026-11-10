"use client";

// 내 정보(웹 탭 · 모바일 화면)가 같이 쓰는 칸: 관심 공고 · 알림 설정 · 제보하기
import { useState } from "react";
import Link from "next/link";
import { Heart } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Toggle } from "@/components/ui/Toggle";
import { usePush } from "@/features/alerts/usePush";
import { useSession } from "@/features/auth/session";
import { useFavoriteToggle, useFavorites, type Favorite } from "@/features/favorites/queries";
import {
  generalReportKinds,
  myReportsKey,
  reportErrorMessage,
  sendReport,
  useMyReports,
  useNotificationSettings,
  type GeneralReportKind,
  type MyReport,
  type NotificationSettings,
} from "@/features/me/api";
import { USE_MOCKS } from "@/lib/api/config";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

/** 2px 테두리 선택 칩 */
export const outlineChip = (on: boolean) =>
  cn(
    "rounded-pill min-h-[44px] cursor-pointer border-2 border-solid text-[15px] font-bold",
    on ? "border-brand bg-brand-soft text-brand-strong" : "border-line bg-surface text-text",
  );

/** 로그인하지 않았을 때 */
export function LoginPrompt({ what }: { what: string }) {
  return (
    <div className="flex flex-col items-center gap-[12px] py-[36px] text-center">
      <span className="text-[17px] font-bold">로그인하면 {what}을(를) 볼 수 있어요</span>
      <Link
        href={routes.login}
        className="bg-brand inline-flex min-h-[48px] items-center rounded-sm px-[18px] text-[15px] font-bold text-white no-underline hover:text-white"
      >
        로그인하기
      </Link>
    </div>
  );
}

/* ── 관심 공고 ─────────────────────────────────────────────────────── */

const typeLabel: Record<Favorite["targetType"], string> = {
  NOTICE: "공고",
  BENEFIT: "혜택",
  STARTUP_SUPPORT: "창업 지원",
  SPACE_RECRUITMENT: "사업공간",
};

const statusLabel: Record<string, string> = {
  UPCOMING: "접수 예정",
  APPLYING: "접수 중",
  OPEN: "접수 중",
  ALWAYS: "상시",
  CLOSED: "마감",
};

/** 오늘(한국 시간)부터 마감일까지 남은 날 */
function daysUntil(date: string) {
  const today = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Seoul" }));
  today.setHours(0, 0, 0, 0);
  const end = new Date(`${date}T00:00:00`);
  return Math.round((end.getTime() - today.getTime()) / 86_400_000);
}

/** 마감 표시와 급한지 (3일 이내) */
export function deadlineOf(f: Pick<Favorite, "applyEnd" | "status">) {
  if (f.status === "CLOSED") return { label: "마감", urgent: false };
  if (f.applyEnd) {
    const d = daysUntil(f.applyEnd);
    if (d < 0) return { label: "마감", urgent: false };
    return { label: d === 0 ? "D-day" : `D-${d}`, urgent: d <= 3 };
  }
  return { label: f.status ? (statusLabel[f.status] ?? "") : "", urgent: false };
}

function FavoriteRow({ f }: { f: Favorite }) {
  const fav = useFavoriteToggle(f.targetType, f.targetId);
  const deadline = deadlineOf(f);
  const gone = !f.title || f.status === "HIDDEN";
  return (
    <div className="border-line-soft flex items-center gap-[14px] border-b border-solid py-[16px]">
      {gone ? (
        <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
          <span className="text-text-sub text-[17px] font-bold">내려간 공고예요</span>
          <span className="text-text-sub text-[14px]">{typeLabel[f.targetType]}</span>
        </span>
      ) : (
        <Link
          href={f.linkPath}
          className="text-text hover:text-text flex min-w-0 flex-1 flex-col gap-[3px] no-underline"
        >
          <span className="text-[17px] font-bold">{f.title}</span>
          <span className="text-text-sub text-[14px]">
            {[typeLabel[f.targetType], f.organization].filter(Boolean).join(" · ")}
          </span>
        </Link>
      )}
      {deadline.label && (
        <span
          className={cn(
            "rounded-badge flex-none px-[10px] py-[5px] text-[13px] font-extrabold",
            deadline.urgent ? "bg-text text-white" : "bg-fill text-text-sub",
          )}
        >
          {deadline.label}
        </span>
      )}
      <button
        type="button"
        aria-label={`${f.title ?? "공고"} 관심 해제`}
        onClick={() => void fav.toggle()}
        className="bg-fill text-brand flex size-[44px] flex-none cursor-pointer items-center justify-center rounded-sm border-0"
      >
        <Heart size={20} fill="currentColor" aria-hidden />
      </button>
    </div>
  );
}

export function FavoriteList() {
  const { items, loading, loggedIn } = useFavorites();
  if (!USE_MOCKS && !loggedIn) return <LoginPrompt what="관심 공고" />;
  if (loading) return <span className="text-text-sub py-[24px] text-[15px]">불러오는 중…</span>;
  return (
    <div className="flex flex-col">
      <span className="text-text-sub pb-[6px] text-[14px]">
        관심 공고의 마감 3일·1일 전과 정정·후속 안내를 알려 드려요
      </span>
      {items.map((f) => (
        <FavoriteRow key={`${f.targetType}:${f.targetId}`} f={f} />
      ))}
      {items.length === 0 && (
        <div className="flex flex-col items-center gap-[12px] py-[40px] text-center">
          <span className="text-[17px] font-bold">관심 공고가 없어요</span>
          <span className="text-text-sub text-[15px]">
            공고 상세에서 하트를 누르면 여기에 모여요
          </span>
          <Link
            href={routes.homes}
            className="bg-brand inline-flex min-h-[48px] items-center rounded-sm px-[18px] text-[15px] font-bold text-white no-underline hover:text-white"
          >
            공고 보러 가기
          </Link>
        </div>
      )}
    </div>
  );
}

/* ── 알림 설정 ─────────────────────────────────────────────────────── */

const settingRows: { key: keyof NotificationSettings; label: string; desc: string }[] = [
  { key: "newNotice", label: "새 공고", desc: "관심 조건에 맞는 주거·사업공간 공고가 나오면" },
  { key: "newSupport", label: "새 지원 정책", desc: "관심 조건에 맞는 혜택·창업 지원이 나오면" },
  { key: "deadline", label: "마감 3일·1일 전", desc: "관심 공고 마감이 다가오면" },
  { key: "correction", label: "정정 공고", desc: "관심 공고 내용이 바뀌면" },
  { key: "followUp", label: "후속 안내", desc: "관심 공고에 발표·추가 안내가 나오면" },
];

export function NotificationSettingsPanel() {
  const settings = useNotificationSettings();
  const push = usePush();
  if (!settings.loggedIn) return <LoginPrompt what="알림 설정" />;
  return (
    <div className="flex flex-col gap-[22px]">
      <div className="flex flex-col">
        {settingRows.map((n) => (
          <div
            key={n.key}
            className="border-line-soft flex items-center justify-between gap-[16px] border-b border-solid py-[14px]"
          >
            <span className="flex flex-col gap-[2px]">
              <span className="text-[16px] font-bold">{n.label}</span>
              <span className="text-text-sub text-[14px]">{n.desc}</span>
            </span>
            <Toggle
              checked={settings.value[n.key]}
              onChange={(v) => settings.set({ [n.key]: v })}
              label={n.label}
            />
          </div>
        ))}
        <div className="flex items-center justify-between gap-[16px] py-[14px]">
          <span className="flex flex-col gap-[2px]">
            <span className="text-[16px] font-bold">방해 금지 · 밤 10시 ~ 아침 8시</span>
            <span className="text-text-sub text-[14px]">
              이 시간에는 푸시를 보내지 않고 아침에 모아 보내요
            </span>
          </span>
          <Toggle
            checked={settings.value.quietEnabled}
            onChange={(v) => settings.set({ quietEnabled: v })}
            label="방해 금지"
          />
        </div>
        <span className="text-text-sub text-[13px]">
          꺼도 알림함에는 남아요. 푸시는 발송하지 않아요
        </span>
        {settings.failed && (
          <span role="alert" className="text-danger-text mt-[6px] text-[14px]">
            저장하지 못했어요. 잠시 뒤 다시 해 주세요
          </span>
        )}
      </div>
      <div className="flex flex-col gap-[10px]">
        <span className="text-[16px] font-extrabold">받는 방법</span>
        <div role="group" aria-label="받는 방법" className="flex flex-wrap items-center gap-[8px]">
          <button
            type="button"
            aria-pressed={push.enabled}
            disabled={push.pending}
            onClick={() => void (push.enabled ? push.turnOff() : push.turnOn())}
            className={cn(outlineChip(push.enabled), "px-[18px]")}
          >
            이 브라우저 · 앱 알림 {push.enabled ? "켜짐" : "꺼짐"}
          </button>
        </div>
        {push.error && (
          <span role="alert" className="text-danger-text text-[14px]">
            {push.error}
          </span>
        )}
      </div>
    </div>
  );
}

/* ── 제보하기 (일반 제보 + 내 제보) ─────────────────────────────────── */

const reportStatus: Record<MyReport["status"], string> = {
  NEW: "받음",
  DOING: "확인 중",
  DONE: "처리 끝",
};

const reportKindLabel: Record<MyReport["kind"], string> = {
  NOTICE: "공고",
  BENEFIT: "혜택",
  PROGRAM: "창업 지원",
  AREA: "생활권",
  GENERAL: "일반",
};

const generalLabel = Object.fromEntries(generalReportKinds.map((k) => [k.key, k.label]));

function MyReportRow({ r }: { r: MyReport }) {
  const what = r.kind === "GENERAL" ? (generalLabel[r.field] ?? r.field) : r.field;
  const title = r.targetTitle ?? (r.kind === "GENERAL" ? "일반 제보" : reportKindLabel[r.kind]);
  return (
    <li className="border-line-soft flex flex-col gap-[6px] border-b border-solid py-[14px]">
      <div className="flex items-center justify-between gap-[10px]">
        {r.linkPath ? (
          <Link href={r.linkPath} className="text-text hover:text-text text-[16px] font-bold">
            {title}
          </Link>
        ) : (
          <span className="text-[16px] font-bold">{title}</span>
        )}
        <span
          className={cn(
            "rounded-badge flex-none px-[10px] py-[5px] text-[13px] font-extrabold",
            r.status === "DONE" ? "bg-brand-soft text-brand-strong" : "bg-fill text-text-sub",
          )}
        >
          {reportStatus[r.status]}
          {r.result && (r.result === "FIXED" ? " · 고쳤어요" : " · 그대로 둬요")}
        </span>
      </div>
      <span className="text-text-sub text-[14px]">
        {reportKindLabel[r.kind]} · {what} · {new Date(r.createdAt).toLocaleDateString("ko-KR")}
      </span>
      {(r.note || r.reportedValue) && (
        <span className="text-[15px] leading-[1.6]">{r.note ?? `맞는 값: ${r.reportedValue}`}</span>
      )}
      {r.reply && (
        <span className="rounded-tile bg-bg px-[14px] py-[10px] text-[15px] leading-[1.6]">
          답변: {r.reply}
        </span>
      )}
    </li>
  );
}

/**
 * 일반 제보 양식(빠진 공고·정책, 틀린 정보, 화면 오류, 기타)과 내 제보 목록.
 * 공고·혜택의 틀린 칸은 그 상세 화면의 「정보가 틀렸어요」로 보내요
 */
export function ReportPanel({
  initialKind = "MISSING_NOTICE",
  screen,
  context,
}: {
  initialKind?: GeneralReportKind;
  /** 어느 화면에서 왔는지 (오류 화면 · 검색 …) */
  screen?: string;
  /** 오류 코드 같은 화면 값 */
  context?: string;
}) {
  const { data: session, isPending } = useSession();
  const reports = useMyReports();
  const client = useQueryClient();
  const [kind, setKind] = useState<GeneralReportKind>(initialKind);
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);
  const loggedIn = USE_MOCKS || !!session;

  if (!loggedIn && !isPending) return <LoginPrompt what="제보" />;

  const submit = async () => {
    if (!note.trim()) {
      setError("내용을 적어 주세요");
      return;
    }
    setState("sending");
    setError(null);
    try {
      await sendReport(null, {
        field: kind,
        note: note.trim(),
        screen: screen ?? "내 정보",
        currentValue: context,
      });
      setState("sent");
      setNote("");
      void client.invalidateQueries({ queryKey: myReportsKey });
    } catch (e) {
      setState("idle");
      setError(reportErrorMessage(e));
    }
  };

  return (
    <div className="flex flex-col gap-[24px]">
      {state === "sent" ? (
        <div
          role="status"
          className="bg-brand-soft flex flex-col items-start gap-[10px] rounded-[20px] p-[24px]"
        >
          <span className="text-brand-strong text-[19px] font-extrabold">제보 고마워요</span>
          <span className="text-brand-strong text-[15px] leading-[1.6]">
            확인한 뒤 알림함과 아래 「내 제보」로 결과를 알려 드릴게요.
          </span>
          <button
            type="button"
            onClick={() => setState("idle")}
            className="text-brand-strong min-h-[44px] cursor-pointer rounded-sm border-0 bg-white px-[16px] text-[15px] font-bold"
          >
            다른 제보하기
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-[16px]">
          <span className="text-text-sub text-[15px] leading-[1.6]">
            빠진 공고·정책이나 화면 오류를 알려 주시면 확인해서 반영해요. 공고의 틀린 내용은 그 공고
            화면의 「정보가 틀렸어요」로 보내 주세요.
          </span>
          <div role="group" aria-label="제보 종류" className="flex flex-wrap gap-[8px]">
            {generalReportKinds.map((k) => (
              <button
                key={k.key}
                type="button"
                aria-pressed={k.key === kind}
                onClick={() => setKind(k.key)}
                className={cn(outlineChip(k.key === kind), "px-[16px]")}
              >
                {k.label}
              </button>
            ))}
          </div>
          <label className="flex flex-col gap-[8px] text-[15px] font-bold">
            자세히 알려주세요
            <textarea
              rows={4}
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={
                kind === "MISSING_NOTICE"
                  ? "예: 마포구 청년주택 2차 모집 공고가 없어요 (기관 · 공고 이름)"
                  : "예: 사업공간 화면에서 지도가 나오지 않아요"
              }
              className="rounded-control border-line bg-surface text-text resize-y border border-solid px-[16px] py-[14px] text-[16px] font-medium"
            />
          </label>
          {error && (
            <span role="alert" className="text-danger-text text-[14px]">
              {error}
            </span>
          )}
          <button
            type="button"
            disabled={state === "sending"}
            onClick={() => void submit()}
            className="rounded-control bg-brand min-h-[52px] cursor-pointer self-start border-0 px-[24px] text-[16px] font-extrabold text-white disabled:opacity-60"
          >
            {state === "sending" ? "보내는 중…" : "제보 보내기"}
          </button>
        </div>
      )}
      <section aria-label="내 제보" className="flex flex-col gap-[4px]">
        <h2 className="m-0 text-[18px] font-extrabold">내 제보</h2>
        {reports.loading ? (
          <span className="text-text-sub py-[12px] text-[15px]">불러오는 중…</span>
        ) : reports.failed ? (
          <span
            role="alert"
            className="text-text-sub flex flex-wrap items-center gap-[8px] py-[12px] text-[15px]"
          >
            내 제보 목록을 불러오지 못했어요. 잠시 뒤 다시 해 주세요
            <button
              type="button"
              onClick={reports.retry}
              className="text-brand cursor-pointer border-0 bg-transparent p-0 text-[15px] font-bold"
            >
              다시 불러오기
            </button>
          </span>
        ) : reports.items.length === 0 ? (
          <span className="text-text-sub py-[12px] text-[15px]">아직 보낸 제보가 없어요</span>
        ) : (
          <ul className="m-0 flex list-none flex-col p-0">
            {reports.items.map((r) => (
              <MyReportRow key={`${r.kind}:${r.id}`} r={r} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
