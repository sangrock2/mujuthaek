import { Suspense } from "react";
import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { businessSummary } from "@/mocks/business";
import { MSpaceDetail } from "@/screens/business/MSpaceDetail";
import { WebSpaceDetail } from "@/screens/business/WebSpaceDetail";

type Params = { params: Promise<{ id: string }> };

export const metadata: Metadata = { title: "공간 상세 | 무주택자들" };

export function generateStaticParams() {
  return businessSummary.list.map((s) => ({ id: s.id }));
}

async function SpaceDetail({ params }: Params) {
  const { id } = await params;
  return <Responsive web={<WebSpaceDetail id={id} />} mobile={<MSpaceDetail id={id} />} />;
}

// params는 Suspense 안에서 읽어요 (Cache Components)
export default function SpaceDetailPage({ params }: Params) {
  return (
    <Suspense>
      <SpaceDetail params={params} />
    </Suspense>
  );
}
