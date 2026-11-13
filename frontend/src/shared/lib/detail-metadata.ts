import type { Metadata } from "next";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { notices } from "@/features/notice/mocks/notice";
import { benefitsSummary } from "@/features/benefits/mocks/benefits";

/** 공개 제목만 읽어요. 개인 조건이나 판정은 메타데이터 요청에 넣지 않아요. */
export async function detailMetadata(kind: "notices" | "benefits", id: string): Promise<Metadata> {
  "use cache";
  let title = kind === "notices" ? "공고 상세" : "혜택 상세";
  if (USE_MOCKS) {
    const items = kind === "notices" ? notices : benefitsSummary.items;
    title = items.find((item) => item.id === id)?.title ?? title;
  } else {
    const origin = process.env.API_ORIGIN ?? process.env.NEXT_PUBLIC_API_BASE_URL;
    if (origin) {
      try {
        const response = await fetch(
          `${origin.replace(/\/$/, "")}/api/v1/${kind}/${encodeURIComponent(id)}`,
          { signal: AbortSignal.timeout(3000) },
        );
        if (response.ok) {
          const detail = (await response.json()) as { header?: { title?: string } };
          title = detail.header?.title || title;
        }
      } catch {
        /* 공개 API를 읽지 못하면 종류별 제목으로 남겨요. */
      }
    }
  }
  return { title: `${title} | 무주택자들`, openGraph: { title: `${title} | 무주택자들` } };
}
