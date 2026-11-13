"use client";

import { useState } from "react";
import Link from "next/link";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { routes } from "@/shared/lib/routes";
import { preparationError, usePreparations, type PreparationStatus } from "./api";
import { scheduleTime } from "./format";

export const statusLabels: Record<PreparationStatus, string> = {
  PREPARING: "준비 중",
  SUBMITTED: "제출 표시",
  ARCHIVED: "보관",
};

export const preparationButton =
  "rounded-control bg-fill text-text min-h-[44px] cursor-pointer border-0 px-[14px] py-[10px] text-[14px] font-bold disabled:opacity-60";

export function ProgressText({ done, total, active }: { done: number; total: number; active: number }) {
  return (
    <span>
      {active === 0 ? "서류 목록 확인 필요" : total === 0 ? "준비 대상 서류 없음" : `서류 ${total}개 중 ${done}개 준비`}
    </span>
  );
}

export function PreparationList() {
  const [status, setStatus] = useState<PreparationStatus>("PREPARING");
  const query = usePreparations(status);

  if (USE_MOCKS) return <p>신청 준비함은 실제 API 연결 후 사용할 수 있어요.</p>;
  if (query.session.isPending) return <p role="status">로그인 확인 중…</p>;
  if (query.session.isError) return <p role="alert">{preparationError(query.session.error)}</p>;
  if (!query.session.data) return <Link href={routes.login}>로그인하고 신청 준비함 사용하기</Link>;

  return (
    <div className="flex flex-col gap-[18px]">
      <p className="text-text-sub m-0 text-[14px]">
        서류와 일정을 확인하고 신청 준비를 이어 가세요. 제출 표시는 직접 기록한 상태예요.
      </p>

      <div className="flex flex-wrap gap-[8px]" aria-label="준비 상태 필터">
        {(Object.keys(statusLabels) as PreparationStatus[]).map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={s === status}
            onClick={() => setStatus(s)}
            className={preparationButton}
          >
            {statusLabels[s]}
          </button>
        ))}
      </div>

      {query.isPending && <p role="status">준비함 불러오는 중…</p>}

      {query.isError && (
        <div role="alert">
          <p>{preparationError(query.error)}</p>

          <button type="button" className={preparationButton} onClick={() => void query.refetch()}>
            다시 시도
          </button>
        </div>
      )}

      {!query.isPending && !query.isError && query.items.length === 0 && (
        <div className="bg-bg rounded-tile p-[20px]">
          <p>아직 {statusLabels[status]}인 공고가 없어요.</p>

          <Link href={`${routes.me}/favorites`}>관심 공고에서 신청 준비하기</Link>
        </div>
      )}

      {query.items.map((p) => (
        <Link
          key={p.id}
          href={routes.preparation(p.id)}
          className="rounded-tile border-line text-text hover:text-text flex flex-col gap-[8px] border border-solid p-[18px] no-underline"
        >
          <strong className="text-[18px]">{p.source.header?.title ?? "현재 공개되지 않은 공고"}</strong>

          <span className="text-text-sub text-[14px]">
            {p.source.header?.provider} · {statusLabels[p.status]}
          </span>

          {p.needsReview && <span className="text-brand-strong text-[14px] font-bold">공고·서류 재확인 필요</span>}

          <ProgressText {...p.progress} />

          <span className="text-[14px] font-semibold">
            내 할 일 {(p.tasks ?? []).filter((t) => !t.done).length}개 남음 · 완료{" "}
            {(p.tasks ?? []).filter((t) => t.done).length}개
          </span>

          {p.nextSchedule && (
            <span className="text-[14px]">
              다음 일정: {p.nextSchedule.label} · {scheduleTime(p.nextSchedule.endsAt)}
            </span>
          )}

          <span className="text-text-sub text-[13px]">
            {p.favorite ? "관심 공고로 등록됨 · 알림 설정에서 수신 관리" : "관심 해제됨 · 관심 기반 알림 중단"}
          </span>
        </Link>
      ))}
    </div>
  );
}
