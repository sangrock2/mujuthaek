import type { PreparationTask } from "./api";

export function koreaDay(date: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export type TaskSort = "created" | "due";

export function sortedTasks(tasks: PreparationTask[], sort: TaskSort = "created"): PreparationTask[] {
  return [...tasks].sort(
    (a, b) =>
      (sort === "due" ? (a.dueOn ?? "9999-12-31").localeCompare(b.dueOn ?? "9999-12-31") : 0) ||
      a.createdAt.localeCompare(b.createdAt) ||
      a.id.localeCompare(b.id),
  );
}

export function taskCounts(tasks: PreparationTask[], today: string) {
  return {
    total: tasks.length,
    done: tasks.filter((t) => t.done).length,
    open: tasks.filter((t) => !t.done).length,
    overdue: tasks.filter((t) => !t.done && t.dueOn != null && t.dueOn < today).length,
    today: tasks.filter((t) => !t.done && t.dueOn === today).length,
  };
}

export function taskDueLabel(task: PreparationTask, today: string) {
  if (!task.dueOn) return "기한 없음";
  if (task.done) return `${task.dueOn.replaceAll("-", ".")} · 완료`;
  if (task.dueOn < today) return `기한 지남 · ${task.dueOn.replaceAll("-", ".")}`;
  if (task.dueOn === today) return "오늘까지";
  return `${task.dueOn.replaceAll("-", ".")}까지`;
}
