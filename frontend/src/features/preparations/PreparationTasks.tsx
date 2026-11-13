"use client";

import { useState, useSyncExternalStore, type FormEvent } from "react";
import { Check, Plus, Pencil, Trash2, CalendarDays, ListChecks } from "lucide-react";
import type { PreparationTask, usePreparation } from "./api";
import { koreaDay, sortedTasks, taskCounts, taskDueLabel, type TaskSort } from "./plan";
import { cn } from "@/shared/lib/cn";
import { preparationButton } from "./PreparationList";

type Mutation = ReturnType<typeof usePreparation>["mutation"];
const inputClass =
  "bg-surface border-line text-text rounded-control min-h-[46px] min-w-0 border border-solid px-[12px] text-[15px]";
const watchDay = (notify: () => void) => {
  const timer = setInterval(notify, 30_000);

  return () => clearInterval(timer);
};
const readDay = () => koreaDay(new Date());
const serverDay = () => "";

function TaskRow({ task, today, mutation }: { task: PreparationTask; today: string; mutation: Mutation }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [due, setDue] = useState(task.dueOn ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pendingDone, setPendingDone] = useState<boolean | null>(null);
  const urgent = !task.done && task.dueOn != null && task.dueOn <= today;

  async function save(e: FormEvent) {
    e.preventDefault();
    await mutation.mutateAsync({
      kind: "task-update",
      task: { ...task, title: title.trim(), dueOn: due || null },
    });
    setEditing(false);
  }

  return (
    <li className="border-line-soft flex flex-col gap-[10px] border-b border-solid py-[16px] last:border-b-0">
      {editing ? (
        <form className="flex flex-col gap-[10px]" onSubmit={(e) => void save(e).catch(() => undefined)}>
          <label className="flex flex-col gap-[6px] text-[14px] font-bold">
            할 일 수정
            <input
              autoFocus
              required
              maxLength={120}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={inputClass}
            />
          </label>
          <label className="flex flex-col gap-[6px] text-[14px]">
            기한 수정 (선택)
            <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className={inputClass} />
          </label>
          <div className="flex gap-[8px]">
            <button disabled={mutation.isPending || !title.trim()} className={preparationButton}>
              수정 저장
            </button>
            <button type="button" onClick={() => setEditing(false)} className={preparationButton}>
              취소
            </button>
          </div>
        </form>
      ) : (
        <div className="flex items-start gap-[10px]">
          <label className="flex min-h-[44px] min-w-0 flex-1 cursor-pointer items-start gap-[12px]">
            <input
              type="checkbox"
              checked={pendingDone ?? task.done}
              aria-label={`${task.title} 완료`}
              disabled={mutation.isPending}
              onChange={(event) => {
                const done = event.currentTarget.checked;
                setPendingDone(done);
                mutation.mutate(
                  { kind: "task-update", task: { ...task, done } },
                  { onSettled: () => setPendingDone(null) },
                );
              }}
              className="accent-brand mt-[2px] size-[22px] flex-none cursor-pointer"
            />
            <span className="flex min-w-0 flex-col gap-[6px]">
              <span className={cn("text-[16px] font-bold break-words", task.done && "text-text-sub line-through")}>
                {task.title}
              </span>
              <span
                className={cn(
                  "flex items-center gap-[5px] text-[13px]",
                  urgent ? "text-check-text font-bold" : "text-text-sub",
                )}
              >
                <CalendarDays size={14} aria-hidden />
                {taskDueLabel(task, today)}
              </span>
            </span>
          </label>
          <button
            type="button"
            title="할 일 수정"
            aria-label={`${task.title} 수정`}
            disabled={mutation.isPending}
            onClick={() => {
              setTitle(task.title);
              setDue(task.dueOn ?? "");
              setEditing(true);
              setConfirmDelete(false);
            }}
            className="text-text-sub flex size-[44px] flex-none cursor-pointer items-center justify-center rounded-sm border-0 bg-transparent"
          >
            <Pencil size={17} aria-hidden />
          </button>
          <button
            type="button"
            title="할 일 삭제"
            aria-label={`${task.title} 삭제`}
            disabled={mutation.isPending}
            onClick={() => setConfirmDelete(!confirmDelete)}
            className="text-text-sub flex size-[44px] flex-none cursor-pointer items-center justify-center rounded-sm border-0 bg-transparent"
          >
            <Trash2 size={17} aria-hidden />
          </button>
        </div>
      )}
      {confirmDelete && (
        <div className="bg-bg rounded-tile flex flex-wrap items-center gap-[8px] p-[12px] text-[14px]">
          <span>이 할 일을 삭제할까요?</span>
          <button
            type="button"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate({ kind: "task-delete", id: task.id })}
            className={preparationButton}
          >
            할 일 삭제하기
          </button>
          <button type="button" onClick={() => setConfirmDelete(false)} className={preparationButton}>
            취소
          </button>
        </div>
      )}
    </li>
  );
}

export function PreparationTasks({
  tasks,
  mutation,
  suggestions = [],
}: {
  tasks: PreparationTask[];
  mutation: Mutation;
  suggestions?: string[];
}) {
  const today = useSyncExternalStore(watchDay, readDay, serverDay);
  const counts = taskCounts(tasks, today);
  const [filter, setFilter] = useState<"all" | "open" | "done" | "overdue">("all");
  const [sort, setSort] = useState<TaskSort>("created");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [message, setMessage] = useState("");
  const shown = sortedTasks(tasks, sort).filter(
    (t) =>
      filter === "all" ||
      (filter === "open" && !t.done) ||
      (filter === "done" && t.done) ||
      (filter === "overdue" && !t.done && t.dueOn != null && t.dueOn < today),
  );

  async function add(e: FormEvent) {
    e.preventDefault();
    await mutation.mutateAsync({ kind: "task-add", title: title.trim(), dueOn: due || null });
    setTitle("");
    setDue("");
    setMessage("할 일을 추가했어요. 계정에 저장되어 다음에도 이어서 볼 수 있어요.");
    setFilter("all");
  }

  return (
    <section id="my-tasks" aria-label="내 할 일 체크리스트" className="scroll-mt-[90px]">
      <div className="mb-[16px] flex items-center justify-between gap-[12px]">
        <span className="flex items-center gap-[8px]">
          <ListChecks className="text-brand" size={24} aria-hidden />
          <h2 className="m-0 text-[22px] font-extrabold">내 할 일 체크리스트</h2>
        </span>
      </div>
      <p className="text-text-sub mt-0 text-[14px] leading-[1.7]">
        이 공고에 신청하려고 내가 해야 할 일을 적어두세요. 공고의 제출 서류는 아래에서 따로 확인할 수 있어요.
      </p>
      <form
        onSubmit={(e) => void add(e).catch(() => undefined)}
        className="bg-bg rounded-tile flex flex-col gap-[12px] p-[16px]"
      >
        <label className="flex flex-col gap-[7px] text-[14px] font-bold">
          새 할 일
          <input
            required
            maxLength={120}
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              setMessage("");
            }}
            placeholder="예: 신청 사이트 가입하고 본인 인증하기"
            className={inputClass}
          />
        </label>
        <div className="flex flex-wrap items-end gap-[10px]">
          <label className="flex min-w-0 flex-[1_1_180px] flex-col gap-[7px] text-[14px]">
            기한 (선택)
            <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className={inputClass} />
          </label>
          <button
            disabled={mutation.isPending || !title.trim() || tasks.length >= 30}
            className="bg-brand rounded-control inline-flex min-h-[46px] cursor-pointer items-center justify-center gap-[6px] border-0 px-[18px] text-[15px] font-bold text-white disabled:opacity-50"
          >
            <Plus size={18} aria-hidden />할 일 추가
          </button>
        </div>
        {tasks.length >= 30 && <span className="text-text-sub text-[13px]">할 일은 30개까지 추가할 수 있어요.</span>}
      </form>
      {tasks.length === 0 && (
        <div className="mt-[12px] flex flex-wrap items-center gap-[8px]">
          <span className="text-text-sub text-[13px]">이런 할 일을 적어볼 수 있어요</span>
          {[...new Set([...suggestions, "신청 사이트 가입하기", "신청 완료 여부 확인하기"])].slice(0, 3).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setTitle(s)}
              className="bg-brand-soft text-brand-strong min-h-[38px] cursor-pointer rounded-sm border-0 px-[10px] text-[13px] font-semibold"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
      <p role="status" className="text-brand-strong my-[10px] text-[13px]">
        {message}
      </p>
      <div className="border-line-soft flex flex-wrap items-center justify-between gap-[10px] border-b border-solid pb-[10px]">
        <div className="flex flex-wrap gap-[6px]" aria-label="할 일 필터">
          {(
            [
              { key: "all", label: `전체 ${counts.total}` },
              { key: "open", label: `진행 중 ${counts.open}` },
              { key: "done", label: `완료 ${counts.done}` },
              { key: "overdue", label: `기한 지남 ${counts.overdue}` },
            ] as const
          ).map((f) => (
            <button
              key={f.key}
              type="button"
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                "min-h-[40px] cursor-pointer rounded-sm border-0 px-[12px] text-[14px] font-bold",
                filter === f.key ? "bg-brand-soft text-brand-strong" : "text-text-sub bg-transparent",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <label className="text-text-sub flex items-center gap-[8px] text-[14px]">
          정렬
          <select
            aria-label="할 일 정렬"
            value={sort}
            onChange={(event) => setSort(event.target.value as TaskSort)}
            className="bg-surface border-line text-text min-h-[40px] rounded-sm border border-solid px-[10px] text-[14px]"
          >
            <option value="created">등록순</option>
            <option value="due">마감 빠른 순</option>
          </select>
        </label>
      </div>
      {shown.length > 0 ? (
        <ul className="m-0 list-none p-0">
          {shown.map((t) => (
            <TaskRow key={`${t.id}:${t.title}:${t.dueOn}`} task={t} today={today} mutation={mutation} />
          ))}
        </ul>
      ) : (
        <div className="text-text-sub flex items-center gap-[8px] py-[22px] text-[14px]">
          <Check size={18} aria-hidden />
          {tasks.length === 0
            ? "아직 할 일이 없어요. 위에서 첫 할 일을 추가해 보세요."
            : filter === "overdue"
              ? "기한이 지난 할 일이 없어요."
              : filter === "done"
                ? "완료한 할 일이 아직 없어요."
                : "진행 중인 할 일을 모두 마쳤어요."}
        </div>
      )}
    </section>
  );
}
