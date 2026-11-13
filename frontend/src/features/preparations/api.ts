"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/features/auth/session";
import { api, ApiError, type Problem } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";

export type PreparationStatus = "PREPARING" | "SUBMITTED" | "ARCHIVED";
export type DocumentState = "TODO" | "DONE" | "NOT_APPLICABLE" | "CHECK_REQUIRED" | "RECHECK_REQUIRED";

export type Evidence = {
  quote: string;
  page: number | null;
  fileId: string | null;
  documentName: string | null;
};

export type Schedule = {
  id: string;
  label: string;
  startsAt: string | null;
  endsAt: string | null;
  description: string | null;
  applicationUrl: string | null;
  timeNote: string | null;
  dailyHours: { start: string; end: string }[];
  breaks?: { start: string; end: string }[];
  channels?: string[];
  places?: { name: string | null; address: string | null; detail: string | null }[];
  applicationEmail?: { address: string; subjectFormat: string | null } | null;
  excludedDays: string[];
  evidence: Evidence[];
};

export type RequiredDocument = {
  id: string;
  name: string;
  group: string | null;
  appliesTo: string | null;
  submissionTime: string | null;
  copies: number | null;
  issuer: string | null;
  description: string | null;
  evidence: Evidence[];
};

export type PreparationTask = {
  id: string;
  title: string;
  dueOn: string | null;
  done: boolean;
  createdAt: string;
};

export type Guidance = {
  id: string;
  kind: string;
  title: string | null;
  description: string | null;
  phone: string | null;
  url: string | null;
  evidence: Evidence[];
};

export type Condition = {
  id: string;
  category: string;
  target: string | null;
  description: string;
  originalText: string | null;
  inReview: boolean;
  evidence: Evidence[];
};

export type UnitType = {
  houseType: string | null;
  siteName: string | null;
  exclusiveM2: number | null;
  depositWon: number | null;
  rentWon: number | null;
  salePriceMinWon: number | null;
  salePriceMaxWon: number | null;
  targetGroups: string[];
};

export type Preparation = {
  id: string;
  noticeId: string;
  status: PreparationStatus;
  submittedAt: string | null;
  revision: number;
  sourceRevision: string;
  acknowledgedSourceRevision: string;
  needsReview: boolean;
  reviewReasons: string[];

  progress: {
    done: number;
    total: number;
    checkRequired: number;
    active: number;
    partial: boolean;
  };

  nextSchedule: Schedule | null;
  favorite: boolean;
  updatedAt: string;
  tasks: PreparationTask[];

  source: {
    header?: {
      title: string;
      provider: string;
      status: string;
      applyEnd: string | null;
      detailUrl: string | null;
    };

    schedules?: Schedule[];
    followUps?: { title: string; detailUrl: string | null; schedules: Schedule[] }[];
    files?: { id: string; name: string; viewUrl: string | null; url: string | null }[];
    guidance?: Guidance[];
    conditions?: Condition[];
    unitTypes?: UnitType[];

    selectionRules?: {
      id: string;
      kind: string;
      description: string;
      originalText: string | null;
      priorityRank: number | null;
      points: number | null;
      maxPoints: number | null;
    }[];
  };

  documents: { source: RequiredDocument; state: DocumentState; active: boolean }[];
  removedDocuments: RequiredDocument[];
};

type Page = { items: Preparation[]; nextCursor: string | null; hasNext: boolean };

export const preparationsKey = ["preparations"] as const;
export const preparationPath = (id: string) => `${endpoints.preparations}/${encodeURIComponent(id)}`;

export function preparationError(error: unknown) {
  if (error instanceof ApiError)
    return (error.body as Problem)?.detail ?? (error.body as Problem)?.title ?? "준비 기록을 저장하지 못했어요";

  return "연결을 확인하고 다시 시도해 주세요";
}

export function usePreparations(status?: PreparationStatus) {
  const session = useSession();
  const query = useQuery({
    queryKey: [...preparationsKey, session.data?.id, "list", status],
    enabled: !USE_MOCKS && !!session.data,

    queryFn: async () => {
      const items: Preparation[] = [];
      let cursor: string | null = null;

      do {
        const params = new URLSearchParams({ size: "100" });
        if (status) params.set("status", status);
        if (cursor) params.set("cursor", cursor);

        const page: Page = await api.get(`${endpoints.preparations}?${params}`);
        items.push(...page.items);
        cursor = page.hasNext ? page.nextCursor : null;
      } while (cursor);

      return items;
    },
  });

  return { ...query, session, items: query.data ?? [] };
}

export function usePreparation(id: string) {
  const session = useSession();
  const client = useQueryClient();
  const key = [...preparationsKey, session.data?.id, "detail", id];

  const query = useQuery<Preparation>({
    queryKey: key,
    enabled: !USE_MOCKS && !!session.data,
    queryFn: () => api.get(preparationPath(id)),
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: (
      action:
        | { kind: "status"; status?: PreparationStatus; restore?: boolean }
        | { kind: "document"; id: string; state: DocumentState }
        | { kind: "acknowledge" }
        | { kind: "delete" }
        | { kind: "task-add"; title: string; dueOn: string | null }
        | { kind: "task-update"; task: PreparationTask }
        | { kind: "task-delete"; id: string },
    ) => {
      const p = query.data;

      if (!p) throw new Error("준비 기록을 먼저 불러와 주세요");

      const path = preparationPath(p.id);
      const body = { expectedRevision: p.revision, sourceRevision: p.sourceRevision };

      if (action.kind === "status")
        return api.patch<Preparation>(path, {
          expectedRevision: p.revision,
          status: action.status,
          restore: action.restore,
        });

      if (action.kind === "document")
        return api.put<Preparation>(`${path}/documents/${encodeURIComponent(action.id)}`, {
          ...body,
          state: action.state,
        });

      if (action.kind === "acknowledge") return api.post<Preparation>(`${path}/acknowledgements`, body);

      if (action.kind === "task-add")
        return api.post<Preparation>(`${path}/tasks`, {
          title: action.title,
          dueOn: action.dueOn,
          expectedRevision: p.revision,
        });

      if (action.kind === "task-update")
        return api.put<Preparation>(`${path}/tasks/${encodeURIComponent(action.task.id)}`, {
          title: action.task.title,
          dueOn: action.task.dueOn,
          done: action.task.done,
          expectedRevision: p.revision,
        });

      if (action.kind === "task-delete")
        return api.delete<Preparation>(`${path}/tasks/${encodeURIComponent(action.id)}?expectedRevision=${p.revision}`);

      return api.delete<Preparation | null>(path);
    },

    onSuccess: (data) => {
      if (data) client.setQueryData(key, data);
      void client.invalidateQueries({ queryKey: preparationsKey });
    },

    onError: (error) => {
      if (error instanceof ApiError && error.status === 409)
        void client.invalidateQueries({ queryKey: preparationsKey });
    },
  });

  return { ...query, session, mutation };
}
