"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MBackHeader } from "@/shared/layout/MBackHeader";
import { WebHeader } from "@/shared/layout/WebHeader";
import { MPage, WebPage } from "@/shared/layout/Responsive";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { routes } from "@/shared/lib/routes";
import { preparationError, usePreparation, type DocumentState, type Schedule } from "./api";
import { preparationButton, ProgressText, statusLabels } from "./PreparationList";
import { noticeStatusLabels, scheduleTime } from "./format";
import { PreparationTasks } from "./PreparationTasks";
import { PreparationSourceInfo } from "./PreparationSourceInfo";

const documentLabels: Record<DocumentState, string> = {
  TODO: "준비 전",
  DONE: "준비 완료",
  NOT_APPLICABLE: "내게 해당 없음",
  CHECK_REQUIRED: "해당 여부 확인",
  RECHECK_REQUIRED: "정정 내용 재확인",
};
const reasonLabels: Record<string, string> = {
  header: "공고 개요·접수 기간",
  requiredDocuments: "제출 서류",
  schedules: "일정",
  followUps: "후속 안내",
  unitTypes: "주택형·금액",
  conditions: "자격 조건",
  heldItems: "확인 필요 항목",
  files: "원문 첨부",
  guidance: "신청 안내",
  selectionRules: "선정 기준",
  NOTICE_MERGED: "공고 병합",
  VERSION_CHANGED: "공고 버전",
  SOURCE_UNAVAILABLE: "원문 공개 중단",
  SOURCE_INCOMPLETE: "서류 식별 정보 확인 필요",
  DOCUMENT_RECHECK: "서류 준비 상태 재확인",
};

function ScheduleRow({ s, from }: { s: Schedule; from?: string }) {
  return (
    <li className="border-line-soft border-b border-solid py-[12px]">
      <strong>{s.label}</strong>
      {from && <span className="text-text-sub"> · {from}</span>}
      <p className="my-[6px]">
        {scheduleTime(s.startsAt)} ~ {scheduleTime(s.endsAt)}
      </p>
      {s.dailyHours.length > 0 && (
        <p className="text-text-sub text-[14px]">
          접수 시각: {s.dailyHours.map((h) => `${h.start}~${h.end}`).join(", ")}
        </p>
      )}
      {s.timeNote && <p>{s.timeNote}</p>}
      {(s.breaks ?? []).length > 0 && (
        <p className="text-text-sub text-[14px]">
          접수 중단 시간: {s.breaks!.map((b) => `${b.start}~${b.end}`).join(", ")}
        </p>
      )}
      {s.excludedDays.length > 0 && <p>접수 제외: {s.excludedDays.join(", ")}</p>}
      {s.description && <p>{s.description}</p>}
      {s.applicationUrl && (
        <a href={s.applicationUrl} target="_blank" rel="noopener noreferrer">
          기관 신청 페이지 열기
        </a>
      )}
    </li>
  );
}

export function PreparationDetail({ id, mobile = false }: { id: string; mobile?: boolean }) {
  const query = usePreparation(id);
  const p = query.data;
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  const Page = mobile ? MPage : WebPage;
  const unavailable = p?.sourceRevision === "unavailable";

  return (
    <Page>
      {mobile ? (
        <MBackHeader title="신청 준비함" backHref={routes.preparations} />
      ) : (
        <WebHeader mode="home" active="me" />
      )}
      <main
        id="main-content"
        tabIndex={-1}
        className="bg-surface rounded-card mx-auto flex w-full max-w-[840px] flex-1 flex-col gap-[24px] px-[20px] py-[28px]"
      >
        <Link href={routes.preparations}>← 신청 준비함</Link>
        {USE_MOCKS ? (
          <p>신청 준비함은 실제 API 연결 후 사용할 수 있어요.</p>
        ) : query.session.isPending ? (
          <p role="status">로그인 확인 중…</p>
        ) : query.session.isError ? (
          <p role="alert">{preparationError(query.session.error)}</p>
        ) : !query.session.data ? (
          <Link href={routes.login}>로그인하고 준비 기록 보기</Link>
        ) : (
          <>
            {query.isPending && <p role="status">준비 기록 불러오는 중…</p>}
            {query.isError && (
              <div role="alert">
                <p>{preparationError(query.error)}</p>
                <button type="button" className={preparationButton} onClick={() => void query.refetch()}>
                  다시 시도
                </button>
              </div>
            )}
            {p && (
              <>
                <header className="flex flex-col gap-[8px]">
                  {process.env.NEXT_PUBLIC_API_PREVIEW === "true" && (
                    <span className="bg-brand-soft text-brand-strong self-start rounded-sm px-[10px] py-[5px] text-[12px] font-bold">
                      예시 공고로 구성한 미리보기
                    </span>
                  )}
                  <span className="text-text-sub">{p.source.header?.provider}</span>
                  <h1 className="m-0 text-[26px] font-extrabold">
                    {p.source.header?.title ?? "현재 공개되지 않은 공고"}
                  </h1>
                  <span>
                    {statusLabels[p.status]} ·{" "}
                    {noticeStatusLabels[p.source.header?.status ?? ""] ?? "공개 상태 확인 필요"}
                  </span>
                  <ProgressText {...p.progress} />
                  {!unavailable && (
                    <span className="text-text-sub text-[14px]">
                      최신 공고 {p.sourceRevision.split(":")[0]}판 · 확인한 공고{" "}
                      {p.acknowledgedSourceRevision.split(":")[0]}판
                    </span>
                  )}
                  {p.progress.partial && <span>공개된 서류 기준 · 원문 확인이 필요한 서류가 있어요</span>}
                  {p.submittedAt && (
                    <span className="text-text-sub text-[14px]">
                      제출했다고 표시한 시각:{" "}
                      {new Date(p.submittedAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} · 실제 접수 확인은
                      기관에서 해 주세요
                    </span>
                  )}
                </header>
                <nav
                  aria-label="신청 준비 목차"
                  className="border-line-soft flex flex-wrap gap-[8px] border-y border-solid py-[12px]"
                >
                  {[
                    { id: "my-tasks", label: "내 할 일" },
                    { id: "documents", label: "제출 서류" },
                    { id: "application-schedules", label: "신청 일정" },
                    { id: "application-method", label: "신청 방법" },
                    { id: "notice-conditions", label: "신청 조건" },
                    { id: "notice-money", label: "금액 확인" },
                  ].map((item) => (
                    <a
                      key={item.id}
                      href={`#${item.id}`}
                      className="bg-fill text-text inline-flex min-h-[38px] items-center rounded-sm px-[12px] text-[13px] font-bold no-underline"
                    >
                      {item.label}
                    </a>
                  ))}
                </nav>
                <div role="status" className="bg-bg rounded-tile p-[16px]">
                  {p.favorite
                    ? "관심 공고로 등록되어 있어요. 알림 설정에서 수신 여부를 관리할 수 있어요."
                    : "관심을 해제했어요. 관심 기반 알림은 중단되지만 준비 기록은 남아 있어요."}
                  <Link className="ml-[8px]" href={`${routes.me}/notifications`}>
                    알림 설정
                  </Link>
                </div>
                {p.needsReview && (
                  <section aria-label="공고 변경 확인" className="bg-brand-soft rounded-tile p-[18px]">
                    <h2 className="mt-0 text-[19px]">공고·서류를 다시 확인해 주세요</h2>
                    <ul>
                      {p.reviewReasons.map((r) => (
                        <li key={r}>{reasonLabels[r] ?? r}</li>
                      ))}
                    </ul>
                    {p.status === "SUBMITTED" && <p>제출 표시 후 공고가 바뀌었어요. 기관에 확인해 주세요.</p>}
                    {!unavailable && (
                      <button
                        type="button"
                        className={preparationButton}
                        disabled={query.mutation.isPending}
                        onClick={() => query.mutation.mutate({ kind: "acknowledge" })}
                      >
                        정정 내용을 확인했어요
                      </button>
                    )}
                    <p className="mb-0 text-[14px]">변경 확인만으로 서류가 준비 완료로 바뀌지는 않아요.</p>
                  </section>
                )}
                {query.mutation.error && <p role="alert">{preparationError(query.mutation.error)}</p>}
                <PreparationTasks
                  tasks={p.tasks ?? []}
                  mutation={query.mutation}
                  suggestions={p.documents
                    .filter((d) => d.state !== "DONE" && d.state !== "NOT_APPLICABLE")
                    .slice(0, 1)
                    .map((d) => `${d.source.name} 발급받기`)}
                />
                {!unavailable && (
                  <>
                    <section aria-label="다음 신청 일정">
                      <h2 className="text-[20px]">다음 신청 일정</h2>
                      <p>
                        {p.needsReview
                          ? "변경된 공고와 서류를 먼저 확인하세요."
                          : p.nextSchedule
                            ? `${p.nextSchedule.label} · ${scheduleTime(p.nextSchedule.endsAt)}`
                            : "다가오는 일정이 확인되지 않아요. 원문과 후속 안내를 확인하세요."}
                      </p>
                    </section>
                    <section id="documents" aria-label="준비할 서류" className="scroll-mt-[90px]">
                      <h2 className="text-[20px]">준비할 서류</h2>
                      <p className="text-text-sub text-[14px] leading-[1.7]">
                        공고에서 확인된 제출 서류예요. 직접 적은 할 일과 별도로 준비 상태를 체크할 수 있어요.
                      </p>
                      {p.documents.length === 0 && <p>확인된 서류 목록이 없어요. 공고 원문에서 확인해 주세요.</p>}
                      {p.documents.map((d) => (
                        <div
                          key={d.source.id}
                          className="border-line-soft flex flex-col gap-[8px] border-b border-solid py-[16px]"
                        >
                          <h3 className="m-0 text-[17px]">{d.source.name}</h3>
                          <span className="text-brand-strong text-[13px] font-bold">
                            {{
                              COMMON: "공통 서류",
                              CONDITIONAL: "해당자 서류",
                              DIRECT: "본인 방문",
                              PROXY_SPOUSE: "배우자 대리 신청",
                              PROXY_OTHER: "기타 대리 신청",
                            }[d.source.group ?? ""] ?? "제출 대상 확인 필요"}
                          </span>
                          <span className="text-text-sub text-[14px]">
                            {[
                              d.source.appliesTo,
                              d.source.issuer && `발급: ${d.source.issuer}`,
                              d.source.submissionTime,
                              d.source.copies != null && `${d.source.copies}부`,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                          {d.source.description && <p className="m-0">{d.source.description}</p>}
                          {!d.source.issuer && (
                            <p className="text-text-sub m-0 text-[13px]">
                              발급 기관 정보가 제공되지 않았어요. 발급처·발급일 조건을 원문에서 확인해 주세요.
                            </p>
                          )}
                          <label className="flex flex-wrap items-center gap-[10px]">
                            준비 상태
                            <select
                              aria-label={`${d.source.name} 준비 상태`}
                              value={d.state}
                              disabled={query.mutation.isPending}
                              onChange={(e) =>
                                query.mutation.mutate({
                                  kind: "document",
                                  id: d.source.id,
                                  state: e.target.value as DocumentState,
                                })
                              }
                              className="border-line bg-surface text-text min-h-[44px] rounded-sm border border-solid px-[12px]"
                            >
                              {(Object.keys(documentLabels) as DocumentState[])
                                .filter((state) => state !== "RECHECK_REQUIRED" || d.state === state)
                                .map((state) => (
                                  <option key={state} value={state} disabled={state === "RECHECK_REQUIRED"}>
                                    {documentLabels[state]}
                                  </option>
                                ))}
                            </select>
                          </label>
                          {d.source.evidence.map((e, i) => (
                            <blockquote key={i} className="text-text-sub mx-0 my-[4px] text-[14px]">
                              {e.quote} {e.page != null && `(${e.page}쪽)`}
                              <Link className="ml-[8px]" href={routes.notice(p.noticeId)}>
                                공고에서 원문 근거 확인
                              </Link>
                            </blockquote>
                          ))}
                        </div>
                      ))}
                      {p.removedDocuments.length > 0 && (
                        <details className="mt-[16px]">
                          <summary>공고에서 빠진 서류 {p.removedDocuments.length}개</summary>
                          <ul>
                            {p.removedDocuments.map((d) => (
                              <li key={d.id}>{d.name} · 준비 개수에서 제외했어요</li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </section>
                    <section id="application-schedules" aria-label="신청 일정" className="scroll-mt-[90px]">
                      <h2 className="text-[20px]">신청 일정과 후속 안내</h2>
                      <ul className="m-0 list-none p-0">
                        {p.source.schedules?.map((s, i) => (
                          <ScheduleRow key={`${s.id}:${i}`} s={s} />
                        ))}
                        {p.source.followUps?.flatMap((f, fi) =>
                          f.schedules.map((s, i) => <ScheduleRow key={`${fi}:${s.id}:${i}`} s={s} from={f.title} />),
                        )}
                      </ul>
                      <p className="text-text-sub text-[14px]">
                        정확한 접수 시각·대상·휴무일은 원문에서 확인해 주세요.
                      </p>
                    </section>
                    <PreparationSourceInfo p={p} />
                    <div className="flex flex-wrap gap-[12px]">
                      <Link className={preparationButton} href={routes.notice(p.noticeId)}>
                        공고와 원문 보기
                      </Link>
                      {p.source.header?.detailUrl && (
                        <a
                          className={preparationButton}
                          href={p.source.header.detailUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          기관 공고 페이지 열기
                        </a>
                      )}
                    </div>
                  </>
                )}
                <section aria-label="준비 상태 관리" className="flex flex-wrap gap-[10px]">
                  {p.status === "ARCHIVED" ? (
                    <button
                      type="button"
                      className={preparationButton}
                      disabled={query.mutation.isPending}
                      onClick={() => query.mutation.mutate({ kind: "status", restore: true })}
                    >
                      보관 전 상태로 복원
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        className={preparationButton}
                        disabled={query.mutation.isPending}
                        onClick={() =>
                          query.mutation.mutate({
                            kind: "status",
                            status: p.status === "SUBMITTED" ? "PREPARING" : "SUBMITTED",
                          })
                        }
                      >
                        {p.status === "SUBMITTED" ? "준비 중으로 되돌리기" : "제출했다고 표시"}
                      </button>
                      <button
                        type="button"
                        className={preparationButton}
                        disabled={query.mutation.isPending}
                        onClick={() => query.mutation.mutate({ kind: "status", status: "ARCHIVED" })}
                      >
                        보관
                      </button>
                    </>
                  )}
                </section>
                <section className="border-line-soft border-t border-solid pt-[18px]">
                  {deleting ? (
                    <div role="group" aria-label="준비 기록 삭제 확인">
                      <p>준비 기록을 삭제할까요? 관심 공고와 알림 설정은 유지돼요.</p>
                      <button
                        type="button"
                        className={preparationButton}
                        disabled={query.mutation.isPending}
                        onClick={() =>
                          query.mutation.mutate(
                            { kind: "delete" },
                            { onSuccess: () => router.replace(routes.preparations) },
                          )
                        }
                      >
                        삭제하기
                      </button>
                      <button type="button" className={preparationButton} onClick={() => setDeleting(false)}>
                        취소
                      </button>
                    </div>
                  ) : (
                    <button type="button" className={preparationButton} onClick={() => setDeleting(true)}>
                      준비 기록 삭제
                    </button>
                  )}
                </section>
              </>
            )}
          </>
        )}
      </main>
    </Page>
  );
}
