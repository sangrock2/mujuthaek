"use client";

// 관심 공고 (마감 D-3·D-1 · 정정 · 후속 안내 알림을 받는 공고). 백엔드 /api/users/me/favorites
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "@/features/auth/session";
import { api, ApiError } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import { routes } from "@/lib/routes";

/** NOTICE 공고 · BENEFIT 혜택 · STARTUP_SUPPORT 창업지원 사업 · SPACE_RECRUITMENT 사업공간 모집 */
export type FavoriteType = "NOTICE" | "BENEFIT" | "STARTUP_SUPPORT" | "SPACE_RECRUITMENT";

/** 관심 목록 한 줄 (백엔드 FavoriteResponse). 대상이 사라졌으면 title·status가 null */
export type Favorite = {
  targetType: FavoriteType;
  targetId: string;
  createdAt: string;
  title: string | null;
  organization: string | null;
  status: string | null;
  applyStart: string | null;
  applyEnd: string | null;
  linkPath: string;
};

type Page = { items: Favorite[]; nextCursor: string | null; hasNext: boolean };

export const favoritesKey = ["favorites"] as const;

/** 경로의 종류 이름 (notice · space-recruitment …) */
const slug = (type: FavoriteType) => type.toLowerCase().replace("_", "-");

/** 저장한 관심 공고 전부 (최대 200개라 두 번이면 끝나요). 로그인하지 않았으면 빈 목록 */
async function fetchAll(): Promise<Favorite[]> {
  const all: Favorite[] = [];
  let cursor: string | null = null;
  do {
    const page: Page = await api.get<Page>(
      `${endpoints.favorites}?size=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    );
    all.push(...page.items);
    cursor = page.hasNext ? page.nextCursor : null;
  } while (cursor);
  return all;
}

export function useFavorites() {
  const session = useSession();
  const loggedIn = !!session.data;
  const q = useQuery({
    queryKey: favoritesKey,
    queryFn: fetchAll,
    enabled: !USE_MOCKS && loggedIn,
    retry: false,
    staleTime: 60 * 1000,
  });
  return {
    items: loggedIn ? (q.data ?? []) : [],
    loading: loggedIn && q.isPending,
    error: q.isError,
    loggedIn,
  };
}

/** 목업 모드: 저장하지 않고 이 화면에서만 켜고 꺼요 */
const mockOn = new Set<string>();

/**
 * 관심 등록 버튼. 누르면 바로 바뀌어 보이고(서버 응답을 기다리지 않음) 실패하면 되돌려요.
 * 로그인하지 않았으면 로그인 화면으로 가요
 */
export function useFavoriteToggle(type: FavoriteType, id: string | undefined) {
  const { items, loggedIn } = useFavorites();
  const client = useQueryClient();
  const router = useRouter();
  const session = useSession();
  const [mock, setMock] = useState(() => (id ? mockOn.has(`${type}:${id}`) : false));
  const [message, setMessage] = useState<string | null>(null);

  const on = USE_MOCKS
    ? mock
    : !!id && items.some((f) => f.targetType === type && f.targetId === id);

  const toggle = async () => {
    if (!id) return;
    setMessage(null);
    if (USE_MOCKS) {
      const key = `${type}:${id}`;
      if (mockOn.has(key)) mockOn.delete(key);
      else mockOn.add(key);
      setMock(mockOn.has(key));
      return;
    }
    if (!loggedIn) {
      if (session.isPending) return;
      router.push(routes.login);
      return;
    }
    const before = client.getQueryData<Favorite[]>(favoritesKey) ?? [];
    const next = on
      ? before.filter((f) => !(f.targetType === type && f.targetId === id))
      : [
          {
            targetType: type,
            targetId: id,
            createdAt: new Date().toISOString(),
            title: null,
            organization: null,
            status: null,
            applyStart: null,
            applyEnd: null,
            linkPath: "",
          },
          ...before,
        ];
    client.setQueryData(favoritesKey, next);
    try {
      if (on) await api.delete(endpoints.favorite(slug(type), id));
      else await api.put(endpoints.favorite(slug(type), id));
    } catch (error) {
      client.setQueryData(favoritesKey, before);
      const code = error instanceof ApiError ? error.code : undefined;
      setMessage(
        code === "FAVORITE_LIMIT_EXCEEDED"
          ? "관심 공고는 200개까지 저장할 수 있어요"
          : "저장하지 못했어요. 잠시 뒤 다시 해 주세요",
      );
    } finally {
      // 제목·마감일이 채워진 목록으로 다시 받아요
      void client.invalidateQueries({ queryKey: favoritesKey });
    }
  };

  return { on, toggle, message };
}
