"use client";

// 「정보가 틀렸어요 · 제보하기」: 누르면 그 자리에 양식이 펼쳐져요. 공고·혜택·사업(사업공간 모집 포함)에 묶인 제보
import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { MessageSquareWarning } from "lucide-react";
import { outlineChip } from "@/components/me/MePanels";
import { useSession } from "@/features/auth/session";
import { myReportsKey, reportErrorMessage, sendReport, type ReportTarget } from "@/features/me/api";
import { USE_MOCKS } from "@/lib/api/config";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

/** 틀린 칸 (백엔드 field로 그대로 보내요) */
const fields = ["자격 조건", "금액", "일정·마감", "신청 방법", "원문 링크", "기타"];

type Props = {
  target: ReportTarget;
  /** 제보한 화면 이름 (공고 상세 · 사업공간 상세 …) */
  screen: string;
  className?: string;
  /** 버튼 글자 크기 등 */
  buttonClassName?: string;
};

export function ReportButton({ target, screen, className, buttonClassName }: Props) {
  const { data: session, isPending } = useSession();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [field, setField] = useState(fields[0]);
  const [reported, setReported] = useState("");
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);
  const loggedIn = USE_MOCKS || !!session;

  const submit = async () => {
    if (!reported.trim() && !note.trim()) {
      setError("맞는 값이나 설명 중 하나는 적어 주세요");
      return;
    }
    setState("sending");
    setError(null);
    try {
      await sendReport(target, {
        field,
        reportedValue: reported.trim() || undefined,
        note: note.trim() || undefined,
        screen,
      });
      setState("sent");
      void client.invalidateQueries({ queryKey: myReportsKey });
    } catch (e) {
      setState("idle");
      setError(reportErrorMessage(e));
    }
  };

  return (
    <div className={cn("flex flex-col gap-[10px]", className)}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "text-text-sub inline-flex min-h-[44px] cursor-pointer items-center gap-[4px] self-center border-0 bg-transparent p-0 text-[14px] font-bold",
          buttonClassName,
        )}
      >
        <MessageSquareWarning size={15} aria-hidden />
        정보가 틀렸어요 · 제보하기
      </button>
      {open && (
        <div className="rounded-tile bg-bg flex flex-col gap-[12px] p-[16px] text-left">
          {!loggedIn && !isPending ? (
            <span className="text-[15px]">
              제보는 로그인하고 보낼 수 있어요 ·{" "}
              <Link href={routes.login} className="text-brand font-bold">
                로그인하기
              </Link>
            </span>
          ) : state === "sent" ? (
            <span role="status" className="text-brand-strong text-[15px] leading-[1.6] font-bold">
              제보 고마워요. 확인한 뒤 알림함과{" "}
              <Link href={`${routes.me}?tab=reports`} className="text-brand-strong underline">
                내 제보
              </Link>
              로 알려 드릴게요.
            </span>
          ) : (
            <>
              <div role="group" aria-label="틀린 항목" className="flex flex-wrap gap-[6px]">
                {fields.map((f) => (
                  <button
                    key={f}
                    type="button"
                    aria-pressed={f === field}
                    onClick={() => setField(f)}
                    className={cn(outlineChip(f === field), "min-h-[40px] px-[12px] text-[14px]")}
                  >
                    {f}
                  </button>
                ))}
              </div>
              <label className="flex flex-col gap-[6px] text-[14px] font-bold">
                맞는 값 (알면)
                <input
                  value={reported}
                  maxLength={200}
                  onChange={(e) => setReported(e.target.value)}
                  placeholder="예: 보증금 2,600만 원"
                  className="rounded-control border-line bg-surface text-text min-h-[44px] border border-solid px-[12px] text-[15px] font-medium"
                />
              </label>
              <label className="flex flex-col gap-[6px] text-[14px] font-bold">
                설명
                <textarea
                  rows={3}
                  maxLength={1000}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="예: 공고문 4쪽에는 소득 기준이 100%로 나와요"
                  className="rounded-control border-line bg-surface text-text resize-y border border-solid px-[12px] py-[10px] text-[15px] font-medium"
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
                className="bg-brand min-h-[44px] cursor-pointer self-start rounded-sm border-0 px-[18px] text-[15px] font-extrabold text-white disabled:opacity-60"
              >
                {state === "sending" ? "보내는 중…" : "제보 보내기"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
